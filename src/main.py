import asyncio
import signal
import sys
import uuid
from contextlib import suppress

import structlog
import uvloop
from ran.routing.core import Core as RANCore

import settings
from lib import chirpstack, healthcheck, mqtt
from lib.logging_conf import configure_logging
from lib.ran_hooks import RanDevicesSyncHook, RanMulticastGroupsSyncHook
from lib.traffic.chirpstack import ChirpstackStatsUpdater, ChirpstackTrafficRouter
from lib.traffic.manager import TrafficManager
from lib.traffic.ran import RanTrafficRouter
from lib.utils import Periodic

STOP_SIGNALS = (signal.SIGHUP, signal.SIGINT, signal.SIGTERM)

logger = structlog.getLogger(__name__)


def get_tags(value: str) -> dict:
    if not value:
        return {}

    parts = value.split("=", 1)
    if len(parts) > 1:
        return {parts[0]: parts[1]}

    return {parts[0]: ""}


async def get_gateway(chirpstack_api: chirpstack.ChirpStackApi, gateway_id: str) -> str:
    gateway = await chirpstack_api.get_gateway(gateway_id)
    if not gateway:
        raise Exception("Gateway not found: {}".format(gateway_id))

    return gateway.gateway.gateway_id


async def healthcheck_live(context):
    pass


async def healthcheck_ready(context):
    pass


async def main(loop):
    configure_logging(log_level=settings.LOG_LEVEL, console_colors=True)
    tags = get_tags(settings.CHIRPSTACK_MATCH_TAGS)
    logger.info("Chirpstack object selector: ", tags=tags)

    chirpstack_api = chirpstack.ChirpStackApi.from_conn_params(
        host=settings.CHIRPSTACK_API_GRPC_HOST,
        port=settings.CHIRPSTACK_API_GRPC_PORT,
        secure=settings.CHIRPSTACK_API_GRPC_SECURE,
        cert_path=settings.CHIRPSTACK_API_GRPC_CERT_PATH,
        jwt_token=settings.CHIRPSTACK_API_TOKEN,
    )
    logger.info(
        "Connected to ChirpStack API",
        host=settings.CHIRPSTACK_API_GRPC_HOST,
        port=settings.CHIRPSTACK_API_GRPC_PORT,
        secure=settings.CHIRPSTACK_API_GRPC_SECURE,
    )

    ran_core = RANCore(access_token=settings.RAN_TOKEN, url=settings.RAN_API_URL)
    await ran_core.connect()
    logger.info("Connected to RAN API", url=settings.RAN_API_URL)

    ran_devices_sync_hook = RanDevicesSyncHook(ran_core=ran_core)
    ran_multicast_groups_sync_hook = RanMulticastGroupsSyncHook(ran_core=ran_core)

    if settings.CHIRPSTACK_TENANT_ID is None:
        if not await chirpstack_api.has_global_api_token():
            logger.error("Invalid api token type")
            print(
                "\nCHIRPSTACK_API_TOKEN you use has lack of 'list tenants' permission, required for multi-tenant mode."
                "\n  - If you want to use ran-bridge for multiple tenants, specify global api key as "
                "CHIRPSTACK_API_TOKEN."
                "\n  - If you want to use ran-bridge for specific tenant with this api key, specify "
                "CHIRPSTACK_TENANT_ID.\n", flush=True
            )
            await ran_core.close()
            return
        logger.warning(
            "CHIRPSTACK_TENANT_ID not set. Starting in multi-tenant mode",
            handling_tenants=[tenant.id async for tenant in chirpstack_api.get_tenants()],
        )
        ran_chirpstack_devices = chirpstack.MultiTenantDeviceList(
            chirpstack_api=chirpstack_api,
            update_hook=ran_devices_sync_hook,
            tags=tags,
        )
        ran_chirpstack_multicast_groups = chirpstack.MultiTenantMulticastGroupList(
            chirpstack_api=chirpstack_api,
            update_hook=ran_multicast_groups_sync_hook,
        )
    else:
        logger.warning("Starting in single-tenant mode", handling_tenants=[settings.CHIRPSTACK_TENANT_ID])
        ran_chirpstack_devices = chirpstack.MultiApplicationDeviceList(
            chirpstack_api=chirpstack_api,
            update_hook=ran_devices_sync_hook,
            tenant_id=settings.CHIRPSTACK_TENANT_ID,
            tags=tags,
        )
        ran_chirpstack_multicast_groups = chirpstack.MultiApplicationMulticastGroupList(
            chirpstack_api=chirpstack_api,
            tenant_id=settings.CHIRPSTACK_TENANT_ID,
            update_hook=ran_multicast_groups_sync_hook,
        )

    # TODO: better sync sequence, without flushing existed devices.
    logger.info("Cleanup RAN device list")
    await ran_core.routing_table.delete_all()
    logger.info("Cleanup done")

    logger.info("Cleanup RAN multicast groups")
    mcg = await ran_core.multicast_groups.get_multicast_groups()
    await ran_core.multicast_groups.delete_multicast_groups([group.addr for group in mcg])
    logger.info("Cleanup done")

    logger.info("Performing initial ChirpStack devices list sync")
    await ran_chirpstack_devices.sync_from_remote()
    logger.info("Devices synced")

    logger.info("Performing initial ChirpStack multicast groups list sync")
    await ran_chirpstack_multicast_groups.sync_from_remote()
    logger.info("Multicast groups synced")

    # Global stop event to stop 'em all!
    stop_event = asyncio.Event()

    def stop_all() -> None:
        stop_event.set()
        logger.warning("Shutting down service! Press ^C again to terminate")

        def terminate():
            sys.exit("\nTerminated!\n")

        for sig in STOP_SIGNALS:
            loop.remove_signal_handler(sig)
            loop.add_signal_handler(sig, terminate)

    for sig in STOP_SIGNALS:
        loop.add_signal_handler(sig, stop_all)

    tasks = set()
    tasks.add(
        Periodic(ran_chirpstack_devices.sync_from_remote).create_task(
            stop_event,
            interval=settings.CHIRPSTACK_DEVICES_REFRESH_PERIOD,
            task_name="update_chirpstack_device_list",
        )
    )
    logger.info("Periodic devices list sync scheduled", task_name="update_chirpstack_device_list")

    tasks.add(
        Periodic(ran_chirpstack_multicast_groups.sync_from_remote).create_task(
            stop_event,
            interval=settings.CHIRPSTACK_DEVICES_REFRESH_PERIOD,
            task_name="update_chirpstack_multicast_groups_list",
        )
    )
    logger.info("Periodic multicast groups list sync scheduled", task_name="update_chirpstack_multicast_groups_list")

    if settings.CHIRPSTACK_MQTT_TOPIC_PREFIX:
        logger.info("Using mqtt topics prefix", topics_prefix=settings.CHIRPSTACK_MQTT_TOPIC_PREFIX)
    chirpstack_mqtt_client = mqtt.MQTTClient(
        settings.CHIRPSTACK_MQTT_SERVER_URI,
        topics_prefix=settings.CHIRPSTACK_MQTT_TOPIC_PREFIX,
        client_id=uuid.uuid4().hex,
    )
    tasks.add(asyncio.create_task(chirpstack_mqtt_client.run(stop_event), name="chirpstack_mqtt_client"))
    logger.info("MQTT client started", task_name="chirpstack_mqtt_client")

    gateway_id: str = await get_gateway(chirpstack_api, settings.CHIRPSTACK_GATEWAY_ID)
    logger.info("Using gateway mac", mac=gateway_id)

    chirpstack_stats_updater = ChirpstackStatsUpdater(
        chirpstack_mqtt_client=chirpstack_mqtt_client,
        gateway_mac=gateway_id,
        stats_metadata={"region_name": settings.CHIRPSTACK_REGION},
    )
    # Initial stats send
    logger.debug("Submitting initial gateway stats")
    await chirpstack_stats_updater.submit_stats()
    tasks.add(
        Periodic(chirpstack_stats_updater.submit_stats).create_task(
            stop_event,
            interval=30,
            task_name="chirpstack_stats_updater",
        ),
    )
    logger.info("Periodic chirpstack stats updating scheduled", task_name="chirpstack_stats_updater")

    chirpstack_router = ChirpstackTrafficRouter(
        gateway_id,
        chirpstack_mqtt_client,
        devices=ran_chirpstack_devices,
        multicast_groups=ran_chirpstack_multicast_groups,
    )
    tasks.add(asyncio.create_task(chirpstack_router.run(stop_event), name="chirpstack_traffic_router"))
    logger.info("Chirpstack traffic router started", task_name="chirpstack_traffic_router")

    ran_router = RanTrafficRouter(ran_core)
    tasks.add(asyncio.create_task(ran_router.run(stop_event), name="ran_traffic_router"))
    logger.info("Ran traffic router started", task_name="ran_traffic_router")

    manager = TrafficManager(chirpstack=chirpstack_router, ran=ran_router)
    tasks.add(asyncio.create_task(manager.run(stop_event), name="traffic_manager"))
    logger.info("TrafficManager started", task_name="traffic_manager")

    healthcheck_server = healthcheck.HealthcheckServer(healthcheck_live, healthcheck_ready, None)
    tasks.add(
        asyncio.create_task(
            healthcheck_server.run(stop_event, settings.HEALTHCHECK_SERVER_HOST, settings.HEALTHCHECK_SERVER_PORT),
            name="health_check",
        )
    )
    logger.info("HealthCheck server started", task_name="health_check")

    tasks.add(asyncio.create_task(stop_event.wait(), name="stop_event_wait"))

    finished, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finished_task = finished.pop()
    logger.warning(f"Task {finished_task.get_name()!r} exited, shutting down gracefully")

    graceful_shutdown_max_time = 20  # seconds
    for task in pending:
        with suppress(asyncio.TimeoutError):
            logger.debug(f"Waiting task {task.get_name()!r} to shutdown gracefully")
            await asyncio.wait_for(task, graceful_shutdown_max_time / len(tasks))
            logger.debug(f"Task {task.get_name()!r} exited")

    # If tasks not exited gracefully, terminate them by cancelling
    for task in pending:
        if not task.done():
            task.cancel()

    for task in pending:
        try:
            await task
        except asyncio.CancelledError:
            logger.warning(f"Task {task.get_name()!r} terminated")

    logger.info("Bye!")


if __name__ == "__main__":
    loop = uvloop.new_event_loop()
    loop.run_until_complete(main(loop))
