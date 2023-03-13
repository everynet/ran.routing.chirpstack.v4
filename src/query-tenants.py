#!/usr/bin/env python

import argparse
import asyncio

from lib import chirpstack
from lib.environs import Env


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
        # TODO: better way to keep in sync with "settings.py" env variables
        env = Env()
        env.read_env()
        chirpstack_api = chirpstack.ChirpStackApi.from_conn_params(
            host=env("CHIRPSTACK_API_GRPC_HOST", "localhost"),
            port=env.int("CHIRPSTACK_API_GRPC_PORT", 8080),
            secure=env.bool("CHIRPSTACK_API_GRPC_SECURE", False),
            cert_path=env("CHIRPSTACK_API_GRPC_CERT_PATH", None),
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
