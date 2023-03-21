from __future__ import annotations

from enum import Enum
from typing import Optional

import pylorawan
from pydantic import BaseModel
from ran.routing.core.domains import (
    DownstreamRadio,
    LoRaModulation,
    TransmissionWindow,
    UpstreamRadio,
    UpstreamRejectResultCode,
)


# Uplink models
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
class UplinkRadioParams(UpstreamRadio):
    pass


class Uplink(BaseModel):
    uplink_id: int
    context_id: bytes
    used_mic: int
    payload: pylorawan.message.PHYPayload
    radio: UplinkRadioParams

    class Config:
        arbitrary_types_allowed = True

    def make_ack(self, dev_eui: str) -> UplinkAck:
        return UplinkAck(uplink_id=self.uplink_id, context_id=self.context_id, mic=self.used_mic, dev_eui=dev_eui)

    def make_reject(self, reason: UplinkRejectReason) -> UplinkReject:
        return UplinkReject(uplink_id=self.uplink_id, context_id=self.context_id, reason=reason)


class UplinkAck(BaseModel):
    uplink_id: int
    context_id: bytes
    mic: int
    dev_eui: str


class UplinkRejectReason(Enum):
    DeviceNotFound = 1
    MicChallengeFail = 2
    InternalError = 3
    NotSupported = 4


class UplinkReject(BaseModel):
    uplink_id: int
    context_id: bytes
    reason: UplinkRejectReason


# Downlink models
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
class DownlinkRadioParams(DownstreamRadio):
    pass


class DownlinkTiming:
    class TimingBase:
        pass

    class Delay(TimingBase, BaseModel):
        seconds: int

    class GpsTime(TimingBase, BaseModel):
        tmms: int

    class Immediately(TimingBase, BaseModel):
        pass

    @classmethod
    def __instancecheck__(cls, instance):
        return isinstance(instance, cls.TimingBase)


class DownlinkDeviceContext:
    class ContextBase:
        pass

    class Regular(ContextBase, BaseModel):
        dev_eui: str
        target_dev_addr: Optional[str]

    class Multicast(ContextBase, BaseModel):
        multicast_addr: str

    @classmethod
    def __instancecheck__(cls, instance):
        return isinstance(instance, cls.ContextBase)


class Downlink(BaseModel):
    downlink_id: int
    context_id: bytes
    payload: bytes

    radio: DownlinkRadioParams
    timing: DownlinkTiming.TimingBase
    device_ctx: Optional[DownlinkDeviceContext.ContextBase]

    class Config:
        arbitrary_types_allowed = True


class DownlinkResultStatus(Enum):
    OK = 0
    ERROR = 1
    TOO_LATE = 2


class DownlinkResult(BaseModel):
    downlink_id: int
    status: DownlinkResultStatus


__all__ = (
    # re-exporting
    "DownstreamRadio",
    "TransmissionWindow",
    "UpstreamRadio",
    "UpstreamRejectResultCode",
    "LoRaModulation",
    # Uplink
    "UplinkRadioParams",
    "Uplink",
    "UplinkAck",
    "UplinkRejectReason",
    "UplinkReject",
    # Downlink
    "DownlinkRadioParams",
    "DownlinkTiming",
    "DownlinkDeviceContext",
    "DownlinkResultStatus",
    "DownlinkResult",
)
