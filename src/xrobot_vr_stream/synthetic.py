"""Small deterministic VR frame source for service and client smoke tests."""

from __future__ import annotations

import time

import numpy as np

from xrobot_vr_stream.protocol import (
  SYNTHETIC_BODY_POSE_CONVENTION,
  VrBodyFrame,
  VrInputFrame,
)


_REST_POSITIONS = np.asarray(
  [
    [0.0, 0.0, 1.0],
    [-0.1, 0.0, 0.9], [0.1, 0.0, 0.9], [0.0, 0.0, 1.15],
    [-0.1, 0.0, 0.5], [0.1, 0.0, 0.5], [0.0, 0.0, 1.3],
    [-0.1, 0.0, 0.1], [0.1, 0.0, 0.1], [0.0, 0.0, 1.45],
    [-0.1, 0.1, 0.0], [0.1, 0.1, 0.0], [0.0, 0.0, 1.6],
    [-0.08, 0.0, 1.52], [0.08, 0.0, 1.52], [0.0, 0.0, 1.78],
    [-0.2, 0.0, 1.5], [0.2, 0.0, 1.5],
    [-0.5, 0.0, 1.35], [0.5, 0.0, 1.35],
    [-0.75, 0.0, 1.3], [0.75, 0.0, 1.3],
    [-0.82, 0.0, 1.3], [0.82, 0.0, 1.3],
  ],
  dtype=np.float32,
)


class SyntheticFrameSource:
  def __init__(self, *, fps: float) -> None:
    self._fps = float(fps)
    self._step = 0

  def start(self) -> None:
    return None

  def read(self) -> VrInputFrame:
    step = self._step
    self._step += 1
    timestamp_ns = int(step * 1_000_000_000 / self._fps)
    poses = np.zeros((24, 7), dtype=np.float32)
    poses[:, :3] = _REST_POSITIONS
    poses[:, 6] = 1.0
    angle = 0.25 * np.sin(2.0 * np.pi * step / max(self._fps * 2.0, 1.0))
    poses[18, 3:7] = _quat_x(angle)
    poses[19, 3:7] = _quat_x(-angle)
    poses[20, 3:7] = _quat_x(1.5 * angle)
    poses[21, 3:7] = _quat_x(-1.5 * angle)
    return VrInputFrame(
      timestamp_ns=timestamp_ns,
      body=VrBodyFrame(
        available=True,
        timestamp_ns=timestamp_ns,
        received_time_ns=time.time_ns(),
        joints_pose=poses,
        source="synthetic",
        coordinate_system="z_up",
        pose_convention=SYNTHETIC_BODY_POSE_CONVENTION,
      ),
    )

  def close(self) -> None:
    return None


def _quat_x(angle: float) -> np.ndarray:
  half = 0.5 * float(angle)
  return np.asarray([np.sin(half), 0.0, 0.0, np.cos(half)], dtype=np.float32)
