#!/usr/bin/env python

import argparse
import asyncio

import grpc

import settings
from lib import chirpstack


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", type=str, help="Username", default="admin", required=False)
    parser.add_argument("--password", type=str, help="Password", default="admin", required=False)
    parser.add_argument("--gateway-id", help="Gateway id (mac)", default="000000000000C0DE", required=False)
    parser.add_argument("--name", type=str, help="Gateway unique name", default="chirpstck-ran-bridge", required=False)
    parser.add_argument("--description", type=str, help="Description", default="Chirpstack RAN gateway", required=False)
    parser.add_argument("--ns-name", type=str, help="Network server name", default="chirpstack")
    parser.add_argument("--ns-addr", type=str, help="Network server address", default="chirpstack-network-server:8000")
    parser.add_argument("--tenant-id", type=str, help="Tenant id", required=True)
    parser.add_argument(
        "--chirpstack-url",
        type=str,
        help="Chirpstack server URL (overrides ENV variables)",
        default=None,
        required=False,
    )
    args = parser.parse_args()
    tenant_id = args.tenant_id

    if args.chirpstack_url:
        chirpstack_api = chirpstack.ChirpStackApi.from_url(args.chirpstack_url)
    else:
        chirpstack_api = chirpstack.ChirpStackApi.from_conn_params(
            host=settings.CHIRPSTACK_API_GRPC_HOST,
            port=settings.CHIRPSTACK_API_GRPC_PORT,
            secure=settings.CHIRPSTACK_API_GRPC_SECURE,
            cert_path=settings.CHIRPSTACK_API_GRPC_CERT_PATH,
        )
    await chirpstack_api.authenticate(args.username, args.password)

    existed_gateway = await chirpstack_api.get_gateway(args.gateway_id)
    if existed_gateway:
        print(f'CHIRPSTACK_GATEWAY_ID="{args.gateway_id}"')
        return

    await chirpstack_api.create_gateway(
        gateway_id=args.gateway_id,
        name="ran-bridge-gw:" + args.gateway_id,
        tenant_id=tenant_id,
        description="Autogenerated by ran-chirpstack-bridge",
    )
    print(f'CHIRPSTACK_GATEWAY_ID="{args.gateway_id}"')


if __name__ == "__main__":
    asyncio.run(main())
