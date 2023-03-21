import asyncio
import secrets
from typing import Any

import pylorawan
import pytest

from lib.traffic.models import DownlinkDeviceContext, DownlinkResult, DownlinkResultStatus

from .conftest import ChirpstackTrafficRouter
from .lorawan import generate_data_message, generate_join_request, UplinkMaker


@pytest.mark.integration
@pytest.mark.upstream
@pytest.mark.parametrize(
    "device_profile", [{"name": "test-uplink-otaa-service-profile", "supports_otaa": True}], indirect=True
)
@pytest.mark.parametrize("application", [{"name": "test-uplink-otaa-application"}], indirect=True)
async def test_otaa_join(
    chirpstack_router: ChirpstackTrafficRouter,
    device_otaa: dict[str, Any],
    make_uplink: UplinkMaker,
):
    # Router must be synced before operations (because device may be added after creating router)
    await chirpstack_router.force_sync()
    # Starting ran-router downstream listening loop
    stop = asyncio.Event()
    listener = asyncio.create_task(chirpstack_router.run(stop))

    device = device_otaa
    message = generate_join_request(
        device["nwk_key"],
        device["app_eui"],
        device["dev_eui"],
    )
    uplink = make_uplink(message)
    uplink_ack = await chirpstack_router.handle_upstream(uplink)
    downlink = await chirpstack_router.downstream_rx.get()
    await chirpstack_router.handle_downstream_result(
        DownlinkResult(downlink_id=downlink.downlink_id, status=DownlinkResultStatus.OK)
    )

    # # Printing packets (debug)
    # print(repr(uplink))
    # print(repr(uplink_ack))
    # print(repr(downlink))

    assert uplink.used_mic == uplink_ack.mic
    assert uplink.context_id == uplink_ack.context_id
    assert uplink.uplink_id == uplink_ack.uplink_id
    assert uplink_ack.dev_eui == device["dev_eui"]

    assert uplink.context_id == downlink.context_id
    assert isinstance(downlink.device_ctx, DownlinkDeviceContext.Regular)
    assert downlink.device_ctx.dev_eui == device["dev_eui"]
    assert downlink.device_ctx.target_dev_addr is not None

    mhdr = pylorawan.message.MHDR.parse(downlink.payload[:1])
    assert mhdr.mtype == pylorawan.message.MType.JoinAccept

    join_accept_payload = pylorawan.message.JoinAccept.parse(downlink.payload, bytes.fromhex(device["nwk_key"]))
    assert join_accept_payload.dev_addr == int(downlink.device_ctx.target_dev_addr, 16)

    # Terminating listener
    stop.set()
    await listener


@pytest.mark.integration
@pytest.mark.upstream
@pytest.mark.parametrize(
    "device_profile", [{"name": "test-uplink-otaa-service-profile", "supports_otaa": True}], indirect=True
)
@pytest.mark.parametrize("application", [{"name": "test-uplink-otaa-application"}], indirect=True)
async def test_otaa_join_and_uplink(
    chirpstack_api,
    chirpstack_router: ChirpstackTrafficRouter,
    device_otaa: dict[str, Any],
    make_uplink: UplinkMaker,
):
    # Router must be synced before operations (because device may be added after creating router)
    await chirpstack_router.force_sync()
    # Starting ran-router downstream listening loop
    stop = asyncio.Event()
    listener = asyncio.create_task(chirpstack_router.run(stop))

    device = device_otaa
    message = generate_join_request(
        device["nwk_key"],
        device["app_eui"],
        device["dev_eui"],
    )
    uplink = make_uplink(message)
    uplink_ack = await chirpstack_router.handle_upstream(uplink)
    downlink = await chirpstack_router.downstream_rx.get()
    await chirpstack_router.handle_downstream_result(
        DownlinkResult(downlink_id=downlink.downlink_id, status=DownlinkResultStatus.OK)
    )

    # # Printing packets (debug)
    # print(repr(uplink))
    # print(repr(uplink_ack))
    # print(repr(downlink))

    assert uplink.used_mic == uplink_ack.mic
    assert uplink.context_id == uplink_ack.context_id
    assert uplink.uplink_id == uplink_ack.uplink_id
    assert uplink_ack.dev_eui == device["dev_eui"]

    assert uplink.context_id == downlink.context_id
    assert isinstance(downlink.device_ctx, DownlinkDeviceContext.Regular)
    assert downlink.device_ctx.dev_eui == device["dev_eui"]
    assert downlink.device_ctx.target_dev_addr is not None

    mhdr = pylorawan.message.MHDR.parse(downlink.payload[:1])
    assert mhdr.mtype == pylorawan.message.MType.JoinAccept

    join_accept_payload = pylorawan.message.JoinAccept.parse(downlink.payload, bytes.fromhex(device["nwk_key"]))
    assert join_accept_payload.dev_addr == int(downlink.device_ctx.target_dev_addr, 16)

    device_activation = await chirpstack_api.get_device_activation(dev_eui=device["dev_eui"])
    dev_addr = device_activation.dev_addr
    message = generate_data_message(
        # The device derives FNwkSIntKey & AppSKey from the NwkKey
        device_activation.app_s_key,
        device_activation.nwk_s_enc_key,
        dev_addr,
        secrets.token_bytes(6),
        confirmed=False,
        f_cnt=0,
    )

    uplink = make_uplink(message)
    uplink_ack = await chirpstack_router.handle_upstream(uplink)
    downlink = await chirpstack_router.downstream_rx.get()
    await chirpstack_router.handle_downstream_result(
        DownlinkResult(downlink_id=downlink.downlink_id, status=DownlinkResultStatus.OK)
    )

    assert uplink.used_mic == uplink_ack.mic
    assert uplink.context_id == uplink_ack.context_id
    assert uplink.uplink_id == uplink_ack.uplink_id
    assert uplink_ack.dev_eui == device["dev_eui"]

    assert uplink.context_id == downlink.context_id
    assert isinstance(downlink.device_ctx, DownlinkDeviceContext.Regular)
    assert downlink.device_ctx.dev_eui == device["dev_eui"]
    assert downlink.device_ctx.target_dev_addr is None

    downlink_payload = pylorawan.message.PHYPayload.parse(downlink.payload)
    assert downlink_payload.mhdr.mtype == pylorawan.message.MType.UnconfirmedDataDown
    assert downlink_payload.payload.fhdr.dev_addr == int(dev_addr, 16)

    # Terminating listener
    stop.set()
    await listener


@pytest.mark.integration
@pytest.mark.upstream
@pytest.mark.parametrize("device_profile", [{"name": "test-uplink-abp-service-profile"}], indirect=True)
@pytest.mark.parametrize("application", [{"name": "test-uplink-abp-application"}], indirect=True)
async def test_abp_uplink(
    chirpstack_router: ChirpstackTrafficRouter,
    device_abp: dict[str, Any],
    make_uplink: UplinkMaker,
):
    # Router must be synced before operations (because device may be added after creating router)
    await chirpstack_router.force_sync()
    # Starting ran-router downstream listening loop
    stop = asyncio.Event()
    listener = asyncio.create_task(chirpstack_router.run(stop))

    device = device_abp
    # Test uplink for joined device
    message = generate_data_message(
        # The device derives FNwkSIntKey & AppSKey from the NwkKey
        device["app_s_key"],
        device["nwk_s_enc_key"],
        device["dev_addr"],
        secrets.token_bytes(6),
        confirmed=False,
        f_cnt=0,
    )
    uplink = make_uplink(message)

    uplink_ack = await chirpstack_router.handle_upstream(uplink)
    downlink = await chirpstack_router.downstream_rx.get()
    await chirpstack_router.handle_downstream_result(
        DownlinkResult(downlink_id=downlink.downlink_id, status=DownlinkResultStatus.OK)
    )

    # # Printing packets (debug)
    # print(repr(uplink))
    # print(repr(uplink_ack))
    # print(repr(downlink))

    assert uplink.used_mic == uplink_ack.mic
    assert uplink.context_id == uplink_ack.context_id
    assert uplink.uplink_id == uplink_ack.uplink_id
    assert uplink_ack.dev_eui == device["dev_eui"]

    assert uplink.context_id == downlink.context_id
    assert isinstance(downlink.device_ctx, DownlinkDeviceContext.Regular)
    assert downlink.device_ctx.dev_eui == device["dev_eui"]
    assert downlink.device_ctx.target_dev_addr is None

    downlink_payload = pylorawan.message.PHYPayload.parse(downlink.payload)
    assert downlink_payload.mhdr.mtype == pylorawan.message.MType.UnconfirmedDataDown
    assert downlink_payload.payload.fhdr.dev_addr == int(device["dev_addr"], 16)

    # Terminating listener
    stop.set()
    await listener
