import asyncio
import uuid

import pytest

from lib.mqtt import MQTTClient

from .ext_chirpstack_api import ChirpStackExtendedApi

# @pytest.fixture
# async def chirpstack_internal_api() -> ChirpStackInternalAPI:
#     try:
#         api = ChirpStackInternalAPI("http://localhost:8080", "admin", "admin")
#         await api.authenticate()
#     except Exception as e:
#         return pytest.exit(f"Could not connect to internal api: {e}")
#     return api


@pytest.fixture
async def chirpstack_mqtt_client() -> MQTTClient:
    # TODO: shutdown tests if could not connect to mqtt
    mqtt_client = MQTTClient("mqtt://localhost:1883", client_id=uuid.uuid4().hex, topics_prefix="eu868")
    stop = asyncio.Event()
    stop.clear()

    client_task = asyncio.create_task(mqtt_client.run(stop))

    yield mqtt_client

    stop.set()
    await client_task


@pytest.fixture
async def chirpstack_api() -> ChirpStackExtendedApi:
    try:
        chirpstack_api = ChirpStackExtendedApi.from_url("http://localhost:8080/")
        await chirpstack_api.authenticate("admin", "admin")
    except Exception as e:
        return pytest.exit(f"Could not connect to grpc api: {e}")
    return chirpstack_api
