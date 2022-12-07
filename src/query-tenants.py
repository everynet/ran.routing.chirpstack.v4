#!/usr/bin/env python

import argparse
import asyncio

import settings
from lib import chirpstack


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", type=str, help="Username", default="admin", required=False)
    parser.add_argument("--password", type=str, help="Password", default="admin", required=False)
    parser.add_argument(
        "--chirpstack-url",
        type=str,
        help="Chirpstack server URL (overrides ENV variables)",
        default=None,
        required=False,
    )
    args = parser.parse_args()

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

    tenants = [tenant async for tenant in chirpstack_api.get_tenants()]

    max_name_len = max(len(t.name) for t in tenants)
    tpl = f"|{{:^{max_name_len + 4}}}|{{:^41}}|{{:^21}}|"
    header = tpl.format("name", "tenant id", "can have gateways")

    print("\n")
    print(header)
    print("-" * len(header))
    for tenant in tenants:
        print(tpl.format(tenant.name, tenant.id, "yes" if tenant.can_have_gateways else "no"))
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
