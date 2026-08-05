"""XRoboToolkit acquisition used exclusively by the VR frame publisher."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import time
from typing import Any

import numpy as np

from xrobot_vr_stream.protocol import (
  XROBOT_BODY_POSE_CONVENTION,
  VrAnalogFrame,
  VrBodyFrame,
  VrButtonFrame,
  VrHandFrame,
  VrMotionTrackerFrame,
  VrPoseFrame,
  VrInputFrame,
)


DEFAULT_XRT_SERVICE_SCRIPT = (
  Path(__file__).resolve().parents[2]
  / "scripts"
  / "start_xrt_service.sh"
)
TRACKING_STALL_TIMEOUT_S = 1.0


class XrtFrameSource:
  def __init__(self, *, start_service: bool = True) -> None:
    self._start_service = bool(start_service)
    self._xrt = None
    self._trace_calls = os.environ.get("XROBOT_VR_TRACE_CALLS", "") == "1"
    self._last_tracking_timestamp_ns: int | None = None
    self._last_tracking_change_monotonic: float | None = None

  def start(self) -> None:
    if self._xrt is not None:
      return
    try:
      import xrobotoolkit_sdk as xrt
    except ImportError as exc:
      raise ImportError(
        "xrobotoolkit_sdk is required by xrobot-vr-publisher"
      ) from exc
    if self._start_service:
      if not DEFAULT_XRT_SERVICE_SCRIPT.is_file():
        raise FileNotFoundError(DEFAULT_XRT_SERVICE_SCRIPT)
      subprocess.run(["bash", str(DEFAULT_XRT_SERVICE_SCRIPT)], check=True)
    xrt.init()
    self._xrt = xrt
    print("[vr-input:xrt] reading headset/controllers/body/trackers")

  def read(self) -> VrInputFrame:
    if self._xrt is None:
      self.start()
    timestamp_ns = _optional_int(self._call("get_time_stamp_ns"))
    self._check_tracking_liveness(timestamp_ns)
    return VrInputFrame(
      timestamp_ns=timestamp_ns,
      analog=VrAnalogFrame(
        left_axis=_optional_axis2(self._call("get_left_axis")),
        right_axis=_optional_axis2(self._call("get_right_axis")),
        left_trigger=_optional_float(self._call("get_left_trigger")),
        right_trigger=_optional_float(self._call("get_right_trigger")),
        left_grip=_optional_float(self._call("get_left_grip")),
        right_grip=_optional_float(self._call("get_right_grip")),
      ),
      buttons=VrButtonFrame(
        a=_optional_bool(self._call("get_A_button")),
        b=_optional_bool(self._call("get_B_button")),
        x=_optional_bool(self._call("get_X_button")),
        y=_optional_bool(self._call("get_Y_button")),
        left_menu=_optional_bool(self._call("get_left_menu_button")),
        right_menu=_optional_bool(self._call("get_right_menu_button")),
        left_axis_click=_optional_bool(self._call("get_left_axis_click")),
        right_axis_click=_optional_bool(self._call("get_right_axis_click")),
      ),
      poses=VrPoseFrame(
        headset=_optional_array(self._call("get_headset_pose")),
        left_controller=_optional_array(self._call("get_left_controller_pose")),
        right_controller=_optional_array(self._call("get_right_controller_pose")),
      ),
      body=self._read_body(),
      motion_trackers=VrMotionTrackerFrame(
        count=_optional_int(self._call("num_motion_data_available")),
        timestamp_ns=_optional_int(self._call("get_motion_timestamp_ns")),
        serial_numbers=_optional_str_tuple(
          self._call("get_motion_tracker_serial_numbers")
        ),
        pose=_optional_array(self._call("get_motion_tracker_pose")),
        velocity=_optional_array(self._call("get_motion_tracker_velocity")),
        acceleration=_optional_array(
          self._call("get_motion_tracker_acceleration")
        ),
      ),
      hands=VrHandFrame(
        left_active=_optional_bool(self._call("get_left_hand_is_active")),
        right_active=_optional_bool(self._call("get_right_hand_is_active")),
        left_tracking_state=_optional_int(
          self._call("get_left_hand_tracking_state")
        ),
        right_tracking_state=_optional_int(
          self._call("get_right_hand_tracking_state")
        ),
      ),
    )

  def close(self) -> None:
    if self._xrt is not None:
      close = getattr(self._xrt, "close", None)
      if close is not None:
        close()
    self._xrt = None

  def _read_body(self) -> VrBodyFrame:
    available = bool(self._call("is_body_data_available"))
    timestamps = _optional_array(self._call("get_body_joints_timestamp"))
    timestamp_ns = (
      int(np.max(timestamps)) if timestamps is not None else None
    )
    available = bool(available and timestamp_ns is not None and timestamp_ns > 0)
    return VrBodyFrame(
      available=available,
      timestamp_ns=timestamp_ns if available else None,
      received_time_ns=time.time_ns(),
      joints_pose=(
        _optional_array(self._call("get_body_joints_pose"))
        if available else None
      ),
      joints_velocity=(
        _optional_array(self._call("get_body_joints_velocity"))
        if available else None
      ),
      joints_acceleration=(
        _optional_array(self._call("get_body_joints_acceleration"))
        if available
        else None
      ),
      source="xrt",
      coordinate_system="y_up",
      pose_convention=XROBOT_BODY_POSE_CONVENTION,
    )

  def _check_tracking_liveness(self, timestamp_ns: int | None) -> None:
    if timestamp_ns is None or timestamp_ns <= 0:
      return
    now = time.monotonic()
    if timestamp_ns != self._last_tracking_timestamp_ns:
      self._last_tracking_timestamp_ns = timestamp_ns
      self._last_tracking_change_monotonic = now
      return
    if (
      self._last_tracking_change_monotonic is not None
      and now - self._last_tracking_change_monotonic
      > TRACKING_STALL_TIMEOUT_S
    ):
      raise RuntimeError(
        "XRT Tracking stream stalled or was preempted by another xrt.init()"
      )

  def _call(self, name: str):
    fn = getattr(self._require_xrt(), name, None)
    if fn is None:
      return None
    return self._timed_call(name, fn)

  def _timed_call(self, name: str, fn):
    if self._trace_calls:
      print(f"[vr-input:xrt] call {name}", flush=True)
    start = time.perf_counter()
    value = fn()
    if self._trace_calls:
      elapsed_ms = (time.perf_counter() - start) * 1000.0
      print(f"[vr-input:xrt] done {name} {elapsed_ms:.2f}ms", flush=True)
    return value

  def _require_xrt(self):
    if self._xrt is None:
      raise RuntimeError("XRoboToolkit is not initialized")
    return self._xrt


def _optional_axis2(value: Any) -> np.ndarray | None:
  if value is None:
    return None
  axis = np.asarray(value, dtype=np.float32).reshape(-1)
  if axis.shape[0] < 2:
    return None
  return np.clip(axis[:2], -1.0, 1.0)


def _optional_array(value: Any) -> np.ndarray | None:
  if value is None:
    return None
  return np.asarray(value, dtype=np.float32).copy()


def _optional_bool(value: Any) -> bool | None:
  value = _first_scalar(value)
  return None if value is None else bool(value)


def _optional_float(value: Any) -> float | None:
  value = _first_scalar(value)
  return None if value is None else float(value)


def _optional_int(value: Any) -> int | None:
  value = _first_scalar(value)
  return None if value is None else int(value)


def _first_scalar(value: Any) -> Any:
  while isinstance(value, (list, tuple)):
    if not value:
      return None
    value = value[0]
  if isinstance(value, np.ndarray):
    if value.size == 0:
      return None
    value = value.reshape(-1)[0]
  return value


def _optional_str_tuple(value: Any) -> tuple[str, ...] | None:
  if value is None:
    return None
  if isinstance(value, str):
    return (value,)
  return tuple(str(item) for item in value)
