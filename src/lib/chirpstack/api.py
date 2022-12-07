import asyncio
from typing import Any, AsyncIterator, Dict, Optional

import grpc
import structlog
from chirpstack_api import api
from chirpstack_api.common import common_pb2
from google.protobuf.empty_pb2 import Empty
from yarl import URL

logger = structlog.getLogger(__name__)


def suppress_rpc_error(codes: Optional[list] = None):
    codes = codes if codes is not None else []

    def wrapped(func):
        async def wrapped(*args, **kwargs):
            try:
                value = func(*args, **kwargs)
                if asyncio.iscoroutine(value):
                    return await value
                return value
            except grpc.aio.AioRpcError as e:
                if e.code() in codes:
                    return None
                raise e

        return wrapped

    return wrapped


def get_grpc_channel(host: str, port: str, secure: bool = True, cert_path: str = None) -> grpc.aio.Channel:
    target_addr = f"{host}:{port}"
    channel = None

    if secure:
        if cert_path is not None:
            with open(cert_path, "rb") as f:
                credentials = grpc.ssl_channel_credentials(f.read())
        else:
            credentials = grpc.ssl_channel_credentials()

        channel = grpc.aio.secure_channel(target_addr, credentials)
    else:
        channel = grpc.aio.insecure_channel(target_addr)

    return channel


def grpc_channel_from_url(url: str) -> grpc.aio.Channel:
    url_obj = URL(url)
    if url_obj.scheme.lower() not in ("http", "https"):
        raise Exception("Please, specify url schema  url")
    return get_grpc_channel(url_obj.host, url_obj.port, url_obj.scheme == "https", None)  # type: ignore


class ChirpStackApi:
    @classmethod
    def from_url(cls, url: str, **kwargs):
        url_obj = URL(url)
        if url_obj.scheme.lower() not in ("http", "https"):
            raise Exception("Please, specify url schema")
        return cls(grpc_channel_from_url(url), **kwargs)

    @classmethod
    def from_conn_params(cls, host: str, port: str, secure: bool = True, cert_path: Optional[str] = None, **kwargs):
        return cls(get_grpc_channel(host, port, secure, cert_path), **kwargs)

    def __init__(self, grpc_channel: grpc.aio.Channel, jwt_token: str = None) -> None:
        self._channel = grpc_channel
        self._jwt_token = jwt_token

    @property
    def jwt_token(self):
        return self._jwt_token

    @property
    def channel(self):
        return self._channel

    @property
    def _auth_token(self):
        if self._jwt_token is None:
            raise Exception("Not authenticated, call 'authenticate' first or specify JWT token")
        return [("authorization", f"Bearer {self._jwt_token}")]

    async def authenticate(self, email: str, password: str) -> bool:
        service = api.InternalServiceStub(self._channel)
        req = api.LoginRequest(email=email, password=password)
        result = await service.Login(req)
        if not result.jwt:
            raise Exception("Wrong credentials, authentication failed")
        self._jwt_token = result.jwt
        return True

    async def _get_paginated_data(self, method: Any, request: Any, batch_size=20) -> AsyncIterator[Any]:
        while True:
            response = await method(request, metadata=self._auth_token)
            request.offset += batch_size
            if not response.result:
                break
            for result in response.result:
                yield result

    async def profile(self) -> api.ProfileResponse:
        return await api.InternalServiceStub(self._channel).Profile(Empty(), metadata=self._auth_token)

    async def get_tenants(self) -> AsyncIterator[api.ListTenantsResponse]:
        user_profile = await self.profile()
        async for tenant in self._get_paginated_data(
            api.TenantServiceStub(self._channel).List, api.ListTenantsRequest(user_id=user_profile.user.id, limit=20)
        ):
            yield tenant

    async def get_applications(self, tenant_id: str, batch_size: int = 20):
        service = api.ApplicationServiceStub(self._channel)
        req = api.ListApplicationsRequest()
        req.limit = batch_size
        req.tenant_id = tenant_id
        req.offset = 0

        async for application in self._get_paginated_data(service.List, req, batch_size):
            yield application

    async def create_api_key(
        self,
        name: str,
        is_admin: bool,
        tenant_id: str | None = None,
        # application_id: int = 0,  # TODO: handle application_id
    ) -> api.CreateApiKeyResponse:
        if is_admin is False:
            tenant_id = tenant_id if tenant_id is not None else (await self.profile()).user.id
        else:
            if tenant_id is not None:
                logger.warning("tenant_id can not be set with is_admin set to True, tenant_id field ignored")
                tenant_id = None

        service = api.InternalServiceStub(self._channel)
        result = await service.CreateApiKey(
            api.CreateApiKeyRequest(
                api_key=api.ApiKey(
                    name=name,
                    is_admin=is_admin,
                    tenant_id=tenant_id,
                )
            ),
            metadata=self._auth_token,
        )
        return result

    async def get_devices(
        self,
        application_id: str,
        multicast_group_id: Optional[str] = None,
        batch_size: int = 20,
    ) -> AsyncIterator[api.DeviceListItem]:
        client = api.DeviceServiceStub(self._channel)

        req = api.ListDevicesRequest()
        req.limit = batch_size
        req.offset = 0
        req.application_id = application_id

        if multicast_group_id is not None:
            req.multicast_group_id = multicast_group_id

        async for device in self._get_paginated_data(client.List, req, batch_size):
            yield device

    @suppress_rpc_error([grpc.StatusCode.NOT_FOUND, grpc.StatusCode.UNAUTHENTICATED])
    async def get_device_keys(self, dev_eui: str):
        client = api.DeviceServiceStub(self._channel)

        req = api.GetDeviceKeysRequest()
        req.dev_eui = dev_eui

        res = await client.GetKeys(req, metadata=self._auth_token)
        return res.device_keys

    async def get_device(self, dev_eui: str) -> api.Device:
        client = api.DeviceServiceStub(self._channel)

        req = api.GetDeviceRequest()
        req.dev_eui = dev_eui

        res = await client.Get(req, metadata=self._auth_token)
        return res.device

    async def get_device_activation(self, dev_eui: str) -> api.DeviceActivation:
        client = api.DeviceServiceStub(self._channel)

        req = api.GetDeviceActivationRequest()
        req.dev_eui = dev_eui

        res = await client.GetActivation(req, metadata=self._auth_token)
        return res.device_activation

    async def get_device_profiles(
        self, tenant_id: str, batch_size: int = 20
    ) -> AsyncIterator[api.ListDeviceProfilesResponse]:
        client = api.DeviceProfileServiceStub(self._channel)
        req = api.ListDeviceProfilesRequest()
        req.tenant_id = tenant_id
        req.limit = batch_size
        req.offset = 0

        async for device_profile in self._get_paginated_data(client.List, req, batch_size):
            yield device_profile

    async def get_device_profile(self, device_profile_id: str) -> api.DeviceProfile:
        client = api.DeviceProfileServiceStub(self._channel)

        req = api.GetDeviceProfileRequest()
        req.id = device_profile_id

        res = await client.Get(req, metadata=self._auth_token)
        return res.device_profile

    async def create_network_server(self, **kwargs) -> int:
        client = api.NetworkServerServiceStub(self._channel)

        req = api.CreateNetworkServerRequest()
        network_server = req.network_server
        network_server.name = kwargs["name"]
        network_server.server = kwargs.get("server", "chirpstack-network-server:8000")  # docker-compose default
        network_server.ca_cert = kwargs.get("ca_cert", "")
        network_server.tls_cert = kwargs.get("tls_cert", "")
        network_server.tls_key = kwargs.get("tls_key", "")
        network_server.routing_profile_ca_cert = kwargs.get("routing_profile_ca_cert", "")
        network_server.routing_profile_tls_cert = kwargs.get("routing_profile_tls_cert", "")
        network_server.routing_profile_tls_key = kwargs.get("routing_profile_tls_key", "")
        network_server.gateway_discovery_enabled = kwargs.get("gateway_discovery_enabled", False)
        network_server.gateway_discovery_interval = kwargs.get("gateway_discovery_interval", 0)
        network_server.gateway_discovery_tx_frequency = kwargs.get("gateway_discovery_tx_frequency", 0)
        network_server.gateway_discovery_dr = kwargs.get("gateway_discovery_dr", 0)

        response = await client.Create(req, metadata=self._auth_token)
        return response.id

    async def create_gateway(
        self,
        gateway_id: str,
        name: str,
        tenant_id: str,
        tags: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        tags = tags if tags is not None else {}
        metadata = metadata if metadata is not None else {}
        client = api.GatewayServiceStub(self._channel)

        location = common_pb2.Location()
        location.latitude = kwargs.get("location", {}).get("latitude", 0.0)
        location.longitude = kwargs.get("location", {}).get("longitude", 0.0)
        location.altitude = kwargs.get("location", {}).get("altitude", 0.0)
        location.accuracy = kwargs.get("location", {}).get("accuracy", 0)
        location.source = getattr(
            common_pb2.LocationSource, kwargs.get("location", {}).get("source", "UNKNOWN").upper()
        )
        req = api.CreateGatewayRequest()
        req.gateway.gateway_id = gateway_id
        req.gateway.name = name
        req.gateway.description = kwargs.get("description", "")
        req.gateway.location.MergeFrom(location)
        req.gateway.tenant_id = tenant_id

        if tags:
            for key, value in tags.items():
                req.gateway.tags[key] = value

        if metadata:
            for key, value in metadata.items():
                req.gateway.metadata[key] = value

        return await client.Create(req, metadata=self._auth_token)

    @suppress_rpc_error([grpc.StatusCode.NOT_FOUND])
    async def get_gateway(self, gateway_id):
        client = api.GatewayServiceStub(self._channel)

        req = api.GetGatewayRequest()
        req.gateway_id = gateway_id

        return await client.Get(req, metadata=self._auth_token)

    async def get_multicast_groups(
        self,
        application_id: str,
        batch_size: int = 20,
    ) -> AsyncIterator[api.MulticastGroupListItem]:
        client = api.MulticastGroupServiceStub(self._channel)
        req = api.ListMulticastGroupsRequest()

        req.limit = batch_size
        req.application_id = application_id
        req.offset = 0

        async for multicast_group in self._get_paginated_data(client.List, req, batch_size):
            yield multicast_group

    async def get_multicast_group(self, group_id: str):  # group_id is str formatted UUID
        client = api.MulticastGroupServiceStub(self._channel)
        req = api.GetMulticastGroupRequest()

        req.id = group_id

        return await client.Get(req, metadata=self._auth_token)
