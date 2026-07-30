"""ZMQ subscriber for complete published VR input frames."""

from __future__ import annotations

import time

import zmq

from xrobot_vr_stream.protocol import VrInputFrame, empty_vr_frame, unpack_vr_frame
from xrobot_vr_stream.service import ensure_local_service


DEFAULT_VR_CONNECT = "tcp://127.0.0.1:5592"


class VrSubscriber:
  def __init__(
    self,
    *,
    connect: str,
    stale_after_s: float = 0.5,
    start_local_service: bool = True,
  ) -> None:
    if stale_after_s <= 0.0:
      raise ValueError("stale_after_s must be positive")
    self._connect = str(connect)
    self._stale_after_s = float(stale_after_s)
    self._start_local_service = bool(start_local_service)
    self._socket: zmq.Socket | None = None
    self._frame = empty_vr_frame()
    self._last_recv_monotonic: float | None = None

  def start(self) -> None:
    if self._socket is not None:
      return
    if self._start_local_service:
      ensure_local_service(self._connect)
    socket = zmq.Context.instance().socket(zmq.SUB)
    socket.setsockopt(zmq.LINGER, 0)
    socket.setsockopt(zmq.RCVHWM, 1)
    socket.setsockopt(zmq.CONFLATE, 1)
    socket.setsockopt(zmq.SUBSCRIBE, b"")
    socket.connect(self._connect)
    self._socket = socket
    print(f"[vr-subscriber] reading complete VR frames from {self._connect}")

  def poll(self) -> VrInputFrame:
    if self._socket is None:
      self.start()
    while self._socket is not None:
      try:
        raw = self._socket.recv(flags=zmq.NOBLOCK)
      except zmq.Again:
        break
      self._frame = unpack_vr_frame(raw)
      self._last_recv_monotonic = time.monotonic()
    if (
      self._last_recv_monotonic is None
      or time.monotonic() - self._last_recv_monotonic > self._stale_after_s
    ):
      return empty_vr_frame(source_status="transport_stale")
    return self._frame

  def stop(self) -> None:
    if self._socket is not None:
      self._socket.close(0)
      self._socket = None
    self._last_recv_monotonic = None
    self._frame = empty_vr_frame()
