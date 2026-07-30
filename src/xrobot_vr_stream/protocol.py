"""Versioned complete VR input frame protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import msgpack
import numpy as np


VR_FRAME_PROTOCOL_VERSION = 4
XROBOT_BODY_POSE_CONVENTION = "xrobot_24_xyz_xyzw"
SYNTHETIC_BODY_POSE_CONVENTION = "synthetic_smpl_24_xyz_xyzw"
VrSourceStatus = Literal[
  "connected",
  "tracking_unavailable",
  "reconnecting",
  "transport_stale",
]


@dataclass(frozen=True)
class VrButtonFrame:
  a: bool | None = None
  b: bool | None = None
  x: bool | None = None
  y: bool | None = None
  left_menu: bool | None = None
  right_menu: bool | None = None
  left_axis_click: bool | None = None
  right_axis_click: bool | None = None


@dataclass(frozen=True)
class VrAnalogFrame:
  left_axis: np.ndarray | None = None
  right_axis: np.ndarray | None = None
  left_trigger: float | None = None
  right_trigger: float | None = None
  left_grip: float | None = None
  right_grip: float | None = None


@dataclass(frozen=True)
class VrPoseFrame:
  headset: np.ndarray | None = None
  left_controller: np.ndarray | None = None
  right_controller: np.ndarray | None = None


@dataclass(frozen=True)
class VrBodyFrame:
  available: bool | None = None
  timestamp_ns: int | None = None
  received_time_ns: int | None = None
  joints_pose: np.ndarray | None = None
  joints_velocity: np.ndarray | None = None
  joints_acceleration: np.ndarray | None = None
  source: str | None = None
  coordinate_system: str | None = None
  pose_convention: str | None = None


@dataclass(frozen=True)
class VrMotionTrackerFrame:
  count: int | None = None
  timestamp_ns: int | None = None
  serial_numbers: tuple[str, ...] | None = None
  pose: np.ndarray | None = None
  velocity: np.ndarray | None = None
  acceleration: np.ndarray | None = None


@dataclass(frozen=True)
class VrHandFrame:
  left_active: bool | None = None
  right_active: bool | None = None
  left_tracking_state: int | None = None
  right_tracking_state: int | None = None


@dataclass(frozen=True)
class VrInputFrame:
  session_id: str = ""
  sequence: int = 0
  publish_timestamp_ns: int = 0
  source_status: VrSourceStatus = "connected"
  source_error: str | None = None
  timestamp_ns: int | None = None
  analog: VrAnalogFrame = field(default_factory=VrAnalogFrame)
  buttons: VrButtonFrame = field(default_factory=VrButtonFrame)
  poses: VrPoseFrame = field(default_factory=VrPoseFrame)
  body: VrBodyFrame = field(default_factory=VrBodyFrame)
  motion_trackers: VrMotionTrackerFrame = field(
    default_factory=VrMotionTrackerFrame
  )
  hands: VrHandFrame = field(default_factory=VrHandFrame)


def pack_vr_frame(frame: VrInputFrame) -> bytes:
  payload = {
    "protocol_version": VR_FRAME_PROTOCOL_VERSION,
    "session_id": frame.session_id,
    "sequence": int(frame.sequence),
    "publish_timestamp_ns": int(frame.publish_timestamp_ns),
    "source_status": frame.source_status,
    "source_error": frame.source_error,
    "timestamp_ns": _optional_int(frame.timestamp_ns),
    "analog": {
      "left_axis": _array_to_list(frame.analog.left_axis),
      "right_axis": _array_to_list(frame.analog.right_axis),
      "left_trigger": _optional_float(frame.analog.left_trigger),
      "right_trigger": _optional_float(frame.analog.right_trigger),
      "left_grip": _optional_float(frame.analog.left_grip),
      "right_grip": _optional_float(frame.analog.right_grip),
    },
    "buttons": {
      name: _optional_bool(getattr(frame.buttons, name))
      for name in (
        "a", "b", "x", "y", "left_menu", "right_menu",
        "left_axis_click", "right_axis_click",
      )
    },
    "poses": {
      "headset": _array_to_list(frame.poses.headset),
      "left_controller": _array_to_list(frame.poses.left_controller),
      "right_controller": _array_to_list(frame.poses.right_controller),
    },
    "body": {
      "available": _optional_bool(frame.body.available),
      "timestamp_ns": _optional_int(frame.body.timestamp_ns),
      "received_time_ns": _optional_int(frame.body.received_time_ns),
      "pose_layout": "xyz_xyzw",
      "joints_pose": _array_to_list(frame.body.joints_pose),
      "joints_velocity": _array_to_list(frame.body.joints_velocity),
      "joints_acceleration": _array_to_list(frame.body.joints_acceleration),
      "source": frame.body.source,
      "coordinate_system": frame.body.coordinate_system,
      "pose_convention": frame.body.pose_convention,
    },
    "motion_trackers": {
      "count": _optional_int(frame.motion_trackers.count),
      "timestamp_ns": _optional_int(frame.motion_trackers.timestamp_ns),
      "serial_numbers": (
        None
        if frame.motion_trackers.serial_numbers is None
        else list(frame.motion_trackers.serial_numbers)
      ),
      "pose": _array_to_list(frame.motion_trackers.pose),
      "velocity": _array_to_list(frame.motion_trackers.velocity),
      "acceleration": _array_to_list(frame.motion_trackers.acceleration),
    },
    "hands": {
      "left_active": _optional_bool(frame.hands.left_active),
      "right_active": _optional_bool(frame.hands.right_active),
      "left_tracking_state": _optional_int(frame.hands.left_tracking_state),
      "right_tracking_state": _optional_int(frame.hands.right_tracking_state),
    },
  }
  return msgpack.packb(payload, use_bin_type=True)


def unpack_vr_frame(data: bytes) -> VrInputFrame:
  payload = msgpack.unpackb(data, raw=False)
  if not isinstance(payload, dict):
    raise TypeError("VR frame payload must be a mapping")
  version = int(payload.get("protocol_version", -1))
  if version != VR_FRAME_PROTOCOL_VERSION:
    raise ValueError(
      f"VR frame protocol version {version} != {VR_FRAME_PROTOCOL_VERSION}; "
      "restart the xrobot-vr-input publisher"
    )
  analog = _mapping(payload, "analog")
  buttons = _mapping(payload, "buttons")
  poses = _mapping(payload, "poses")
  body = _mapping(payload, "body")
  trackers = _mapping(payload, "motion_trackers")
  hands = _mapping(payload, "hands")
  if body.get("pose_layout") != "xyz_xyzw":
    raise ValueError("VR body pose_layout must be 'xyz_xyzw'")
  source_status = str(payload.get("source_status"))
  if source_status not in (
    "connected", "tracking_unavailable", "reconnecting", "transport_stale"
  ):
    raise ValueError(f"unsupported VR source_status {source_status!r}")
  serial_numbers = trackers.get("serial_numbers")
  return VrInputFrame(
    session_id=str(payload["session_id"]),
    sequence=int(payload["sequence"]),
    publish_timestamp_ns=int(payload["publish_timestamp_ns"]),
    source_status=source_status,
    source_error=_optional_str(payload.get("source_error")),
    timestamp_ns=_optional_int(payload.get("timestamp_ns")),
    analog=VrAnalogFrame(
      left_axis=_list_to_array(analog.get("left_axis")),
      right_axis=_list_to_array(analog.get("right_axis")),
      left_trigger=_optional_float(analog.get("left_trigger")),
      right_trigger=_optional_float(analog.get("right_trigger")),
      left_grip=_optional_float(analog.get("left_grip")),
      right_grip=_optional_float(analog.get("right_grip")),
    ),
    buttons=VrButtonFrame(**{
      name: _optional_bool(buttons.get(name))
      for name in (
        "a", "b", "x", "y", "left_menu", "right_menu",
        "left_axis_click", "right_axis_click",
      )
    }),
    poses=VrPoseFrame(
      headset=_list_to_array(poses.get("headset")),
      left_controller=_list_to_array(poses.get("left_controller")),
      right_controller=_list_to_array(poses.get("right_controller")),
    ),
    body=VrBodyFrame(
      available=_optional_bool(body.get("available")),
      timestamp_ns=_optional_int(body.get("timestamp_ns")),
      received_time_ns=_optional_int(body.get("received_time_ns")),
      joints_pose=_list_to_array(body.get("joints_pose")),
      joints_velocity=_list_to_array(body.get("joints_velocity")),
      joints_acceleration=_list_to_array(body.get("joints_acceleration")),
      source=_optional_str(body.get("source")),
      coordinate_system=_optional_str(body.get("coordinate_system")),
      pose_convention=_optional_str(body.get("pose_convention")),
    ),
    motion_trackers=VrMotionTrackerFrame(
      count=_optional_int(trackers.get("count")),
      timestamp_ns=_optional_int(trackers.get("timestamp_ns")),
      serial_numbers=(
        None if serial_numbers is None
        else tuple(str(value) for value in serial_numbers)
      ),
      pose=_list_to_array(trackers.get("pose")),
      velocity=_list_to_array(trackers.get("velocity")),
      acceleration=_list_to_array(trackers.get("acceleration")),
    ),
    hands=VrHandFrame(
      left_active=_optional_bool(hands.get("left_active")),
      right_active=_optional_bool(hands.get("right_active")),
      left_tracking_state=_optional_int(hands.get("left_tracking_state")),
      right_tracking_state=_optional_int(hands.get("right_tracking_state")),
    ),
  )


def empty_vr_frame(
  *,
  source_status: VrSourceStatus = "transport_stale",
  source_error: str | None = None,
) -> VrInputFrame:
  return VrInputFrame(
    source_status=source_status,
    source_error=source_error,
    body=VrBodyFrame(available=False),
  )


def _mapping(payload: dict[str, Any], name: str) -> dict[str, Any]:
  value = payload.get(name)
  if not isinstance(value, dict):
    raise TypeError(f"VR frame {name} must be a mapping")
  return value


def _array_to_list(value: Any) -> list[Any] | None:
  if value is None:
    return None
  array = np.asarray(value)
  if not np.issubdtype(array.dtype, np.number) or not np.all(np.isfinite(array)):
    raise ValueError("VR frame arrays must contain finite numbers")
  return array.tolist()


def _list_to_array(value: Any) -> np.ndarray | None:
  if value is None:
    return None
  array = np.asarray(value, dtype=np.float32)
  if not np.all(np.isfinite(array)):
    raise ValueError("VR frame arrays must contain finite numbers")
  return array


def _optional_bool(value: Any) -> bool | None:
  return None if value is None else bool(value)


def _optional_float(value: Any) -> float | None:
  if value is None:
    return None
  result = float(value)
  if not np.isfinite(result):
    raise ValueError("VR frame scalar values must be finite")
  return result


def _optional_int(value: Any) -> int | None:
  return None if value is None else int(value)


def _optional_str(value: Any) -> str | None:
  return None if value is None else str(value)
