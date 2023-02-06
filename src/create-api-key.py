#!/usr/bin/env python

import argparse
import asyncio

import settings
from lib import chirpstack


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", type=str, help="Username", default="admin", required=False)
    parser.add_argument("--password", type=str, help="Password", default="admin", required=False)
    parser.add_argument("--not-admin", help="Admin flag", action="store_true", default=False)
    parser.add_argument("--tenant-id", type=str, help="Tenant id", required=False, default=None)
    parser.add_argument("--key-name", type=str, help="API key name", required=False, default="ran-chirpstack-bridge")
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
    new_api_key = await chirpstack_api.create_api_key(
        name=args.key_name,
        is_admin=(not args.not_admin),
        tenant_id=tenant_id,
    )
    print(f'CHIRPSTACK_API_TOKEN="{new_api_key.token}"')


if __name__ == "__main__":
    asyncio.run(main())
