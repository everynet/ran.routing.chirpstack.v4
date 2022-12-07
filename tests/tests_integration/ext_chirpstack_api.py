from typing import Optional

import grpc
from chirpstack_api import api
from chirpstack_api.common import common_pb2

from lib.chirpstack.api import ChirpStackApi, suppress_rpc_error


class ChirpStackExtendedApi(ChirpStackApi):
    @suppress_rpc_error([grpc.StatusCode.NOT_FOUND, grpc.StatusCode.UNAUTHENTICATED])
    async def get_device(self, dev_eui: str) -> api.Device:
        client = api.DeviceServiceStub(self._channel)

        req = api.GetDeviceRequest()
        req.dev_eui = dev_eui

        res = await client.Get(req, metadata=self._auth_token)
        return res.device

    async def create_device_keys(self, dev_eui: str, nwk_key: str, app_key: Optional[str] = None) -> None:
        client = api.DeviceServiceStub(self._channel)

        req = api.CreateDeviceKeysRequest()
        req.device_keys.dev_eui = dev_eui
        req.device_keys.nwk_key = nwk_key
        req.device_keys.app_key = app_key
        # req.device_keys.gen_app_key = ...

        await client.CreateKeys(req, metadata=self._auth_token)

    async def activate_device(self, dev_eui: str, **kwargs) -> None:
        import secrets

        client = api.DeviceServiceStub(self._channel)

        req = api.ActivateDeviceRequest()
        device_activation = req.device_activation

        device_activation.dev_eui = dev_eui
        device_activation.dev_addr = kwargs.get("dev_addr", secrets.token_hex(4))
        device_activation.app_s_key = kwargs.get("app_s_key", secrets.token_hex(16))
        device_activation.nwk_s_enc_key = kwargs.get("nwk_s_enc_key", secrets.token_hex(16))

        device_activation.s_nwk_s_int_key = kwargs.get("s_nwk_s_int_key", device_activation.nwk_s_enc_key)
        device_activation.f_nwk_s_int_key = kwargs.get("f_nwk_s_int_key", device_activation.nwk_s_enc_key)

        device_activation.f_cnt_up = kwargs.get("f_cnt_up", 0)
        device_activation.n_f_cnt_down = kwargs.get("n_f_cnt_down", 0)
        device_activation.a_f_cnt_down = kwargs.get("a_f_cnt_down", 0)

        await client.Activate(req, metadata=self._auth_token)

    # @suppress_rpc_error([grpc.StatusCode.NOT_FOUND, grpc.StatusCode.UNAUTHENTICATED])
    # async def deactivate_device(self, dev_eui: str) -> None:
    #     client = api.DeviceServiceStub(self._channel)

    #     req = api.DeactivateDeviceRequest()
    #     req.dev_eui = dev_eui

    #     await client.Deactivate(req, metadata=self._auth_token)

    async def delete_device_profile(self, device_profile_id: str) -> None:
        client = api.DeviceProfileServiceStub(self._channel)

        req = api.DeleteDeviceProfileRequest()
        req.id = device_profile_id

        await client.Delete(req, metadata=self._auth_token)

    async def create_device_profile(self, **kwargs):
        client = api.DeviceProfileServiceStub(self._channel)

        req = api.CreateDeviceProfileRequest()
        device_profile = req.device_profile
        device_profile.name = kwargs["name"]
        device_profile.tenant_id = kwargs["tenant_id"]
        device_profile.description = kwargs.get("description", "")
        device_profile.region = kwargs.get("region", common_pb2.Region.EU868)
        device_profile.mac_version = kwargs.get("mac_version", common_pb2.MacVersion.LORAWAN_1_0_3)
        device_profile.reg_params_revision = kwargs.get("reg_params_revision", common_pb2.RegParamsRevision.RP002_1_0_2)
        device_profile.adr_algorithm_id = kwargs.get("adr_algorithm_id", "default")
        device_profile.payload_codec_runtime = kwargs.get("payload_codec_runtime", 0)
        device_profile.payload_codec_script = kwargs.get("payload_codec_script", b"")
        device_profile.flush_queue_on_activate = kwargs.get("flush_queue_on_activate", False)
        device_profile.uplink_interval = kwargs.get("uplink_interval", 1000 * 60 * 5)
        device_profile.device_status_req_interval = kwargs.get("device_status_req_interval", 1)
        device_profile.supports_otaa = kwargs.get("supports_otaa", False)
        device_profile.supports_class_b = kwargs.get("supports_class_b", False)
        device_profile.supports_class_c = kwargs.get("supports_class_c", False)
        device_profile.class_b_timeout = kwargs.get("class_b_timeout", 0)
        device_profile.class_b_ping_slot_period = kwargs.get("class_b_ping_slot_period", 0)
        device_profile.class_b_ping_slot_dr = kwargs.get("class_b_ping_slot_dr", 0)
        device_profile.class_b_ping_slot_freq = kwargs.get("class_b_ping_slot_freq", 0)
        device_profile.class_c_timeout = kwargs.get("class_c_timeout", 0)
        device_profile.abp_rx1_delay = kwargs.get("abp_rx1_delay", 1)
        device_profile.abp_rx1_dr_offset = kwargs.get("abp_rx1_dr_offset", 0)
        device_profile.abp_rx2_dr = kwargs.get("abp_rx2_dr", 0)
        device_profile.abp_rx2_freq = kwargs.get("abp_rx2_freq", 0)
        device_profile.tags.clear()
        for k, v in kwargs.get("tags", {}).items():
            device_profile.tags[k] = v

        res = await client.Create(req, metadata=self._auth_token)
        return res.id

    async def create_device(self, **kwargs) -> str:
        client = api.DeviceServiceStub(self._channel)

        req = api.CreateDeviceRequest()
        req.device.dev_eui = kwargs["dev_eui"]
        req.device.name = kwargs["name"]
        req.device.application_id = kwargs["application_id"]
        req.device.description = kwargs.get("description", "")
        req.device.device_profile_id = kwargs["device_profile_id"]
        req.device.is_disabled = kwargs.get("is_disabled", False)
        req.device.skip_fcnt_check = kwargs.get("skip_fcnt_check", True)
        req.device.tags.update(kwargs.get("tags", {}))

        await client.Create(req, metadata=self._auth_token)
        return kwargs["dev_eui"]

    async def delete_device(self, dev_eui):
        client = api.DeviceServiceStub(self._channel)

        req = api.DeleteDeviceRequest()
        req.dev_eui = dev_eui

        return await client.Delete(req, metadata=self._auth_token)

    async def create_application(self, **kwargs) -> int:
        client = api.ApplicationServiceStub(self._channel)

        req = api.CreateApplicationRequest()
        application = req.application
        application.name = kwargs["name"]
        application.description = kwargs.get("description", "")
        application.tenant_id = kwargs["tenant_id"]

        response = await client.Create(req, metadata=self._auth_token)
        return response.id

    @suppress_rpc_error([grpc.StatusCode.NOT_FOUND, grpc.StatusCode.UNAUTHENTICATED])
    async def get_application(self, application_id: int):
        client = api.ApplicationServiceStub(self._channel)

        req = api.GetApplicationRequest()
        req.id = application_id

        res = await client.Get(req, metadata=self._auth_token)
        return res.application

    async def delete_application(self, application_id: int):
        client = api.ApplicationServiceStub(self._channel)

        req = api.DeleteApplicationRequest()
        req.id = application_id

        return await client.Delete(req, metadata=self._auth_token)

    async def delete_gateway(self, gateway_id):
        client = api.GatewayServiceStub(self._channel)

        req = api.DeleteGatewayRequest()
        req.gateway_id = gateway_id

        return await client.Delete(req, metadata=self._auth_token)

    # async def stream_frame_logs(self, dev_eui, timeout=None):
    #     client = api.DeviceServiceStub(self._channel)

    #     req = api.StreamDeviceFrameLogsRequest()
    #     req.dev_eui = dev_eui

    #     frame_logs = client.StreamFrameLogs(req, metadata=self._auth_token)
    #     frame_logs_iter = frame_logs.__aiter__()

    #     while True:
    #         message = await asyncio.wait_for(frame_logs_iter.__anext__(), timeout=timeout)
    #         yield message

    # async def stream_event_logs(self, dev_eui, timeout=None):
    #     client = api.DeviceServiceStub(self._channel)

    #     req = api.StreamDeviceEventLogsRequest()
    #     req.dev_eui = dev_eui

    #     event_logs = client.StreamEventLogs(req, metadata=self._auth_token)
    #     event_logs_iter = event_logs.__aiter__()

    #     while True:
    #         message = await asyncio.wait_for(event_logs_iter.__anext__(), timeout=timeout)
    #         yield message
