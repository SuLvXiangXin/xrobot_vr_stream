from __future__ import annotations

from types import SimpleNamespace
import time
import unittest
from unittest import mock
import uuid

import msgpack
import numpy as np
import zmq

from xrobot_vr_stream import (
  XROBOT_BODY_POSE_CONVENTION,
  VrAnalogFrame,
  VrBodyFrame,
  VrButtonFrame,
  VrInputFrame,
  VrSubscriber,
  empty_vr_frame,
  pack_vr_frame,
  unpack_vr_frame,
)
import xrobot_vr_stream.publisher as publisher


class VrStreamTest(unittest.TestCase):
  def test_protocol_round_trip_and_fanout(self) -> None:
    body_pose = np.zeros((24, 7), dtype=np.float32)
    body_pose[:, 6] = 1.0
    frame = VrInputFrame(
      session_id="session",
      sequence=7,
      publish_timestamp_ns=time.time_ns(),
      timestamp_ns=123,
      analog=VrAnalogFrame(left_axis=np.array([0.25, -0.5])),
      buttons=VrButtonFrame(a=True),
      body=VrBodyFrame(
        available=True,
        timestamp_ns=120,
        received_time_ns=456,
        joints_pose=body_pose,
        source="xrt",
        coordinate_system="y_up",
        pose_convention=XROBOT_BODY_POSE_CONVENTION,
      ),
    )
    decoded = unpack_vr_frame(pack_vr_frame(frame))
    self.assertEqual(decoded.sequence, 7)
    self.assertTrue(decoded.buttons.a)
    self.assertEqual(
      decoded.body.pose_convention,
      XROBOT_BODY_POSE_CONVENTION,
    )

    endpoint = f"inproc://vr-{uuid.uuid4().hex}"
    socket = zmq.Context.instance().socket(zmq.PUB)
    socket.bind(endpoint)
    subscribers = [
      VrSubscriber(connect=endpoint, stale_after_s=0.01),
      VrSubscriber(connect=endpoint, stale_after_s=0.01),
    ]
    for subscriber in subscribers:
      subscriber.start()
    try:
      deadline = time.monotonic() + 0.5
      received = [subscriber.poll() for subscriber in subscribers]
      while not all(item.buttons.a for item in received):
        if time.monotonic() >= deadline:
          self.fail("subscribers did not receive the VR frame")
        socket.send(pack_vr_frame(frame))
        time.sleep(0.005)
        received = [subscriber.poll() for subscriber in subscribers]
      time.sleep(0.02)
      self.assertEqual(
        subscribers[0].poll().source_status,
        "transport_stale",
      )
    finally:
      for subscriber in subscribers:
        subscriber.stop()
      socket.close(0)

  def test_default_subscriber_ensures_local_service(self) -> None:
    with mock.patch(
      "xrobot_vr_stream.subscriber.ensure_local_service"
    ) as ensure:
      subscriber = VrSubscriber(connect="tcp://127.0.0.1:5592")
      subscriber.start()
      subscriber.stop()
    ensure.assert_called_once_with("tcp://127.0.0.1:5592")

  def test_old_protocol_reports_restart_instruction(self) -> None:
    payload = msgpack.packb({"protocol_version": 3}, use_bin_type=True)
    with self.assertRaisesRegex(ValueError, "restart.*publisher"):
      unpack_vr_frame(payload)

  def test_retry_publishes_reconnecting_heartbeat(self) -> None:
    class _Socket:
      def __init__(self) -> None:
        self.sent = []

      def send(self, payload) -> None:
        self.sent.append(payload)

    socket = _Socket()
    sequence = publisher._send_retry_heartbeats(
      socket,
      session_id="retry-session",
      sequence=4,
      error="SDK unavailable",
      duration_s=0.0,
    )
    frame = unpack_vr_frame(socket.sent[0])
    self.assertEqual(sequence, 5)
    self.assertEqual(frame.source_status, "reconnecting")
    self.assertEqual(frame.source_error, "SDK unavailable")

  def test_publisher_retries_without_rebinding(self) -> None:
    class _Socket:
      def __init__(self) -> None:
        self.sent = []
        self.closed = False

      def send(self, payload) -> None:
        self.sent.append(payload)

      def close(self, linger) -> None:
        self.closed = True

    class _XrtSource:
      instances = []

      def __init__(self, *, start_service: bool) -> None:
        self.start_service = start_service
        self.closed = False
        self.instances.append(self)

      def start(self) -> None:
        if len(self.instances) == 1:
          raise RuntimeError("transient XRT failure")

      def read(self):
        return empty_vr_frame()

      def close(self) -> None:
        self.closed = True

    socket = _Socket()
    args = SimpleNamespace(
      source="xrt",
      bind="inproc://unused",
      fps=30.0,
      frames=1,
      start_service=False,
    )
    with (
      mock.patch.object(publisher, "_parse_args", return_value=args),
      mock.patch.object(publisher, "_publisher_socket", return_value=socket),
      mock.patch.object(publisher, "XrtFrameSource", _XrtSource),
      mock.patch.object(
        publisher,
        "_send_retry_heartbeats",
        side_effect=lambda socket, **kwargs: kwargs["sequence"] + 1,
      ),
    ):
      publisher.main()

    self.assertEqual(len(_XrtSource.instances), 2)
    self.assertTrue(_XrtSource.instances[0].closed)
    self.assertTrue(_XrtSource.instances[1].closed)
    self.assertEqual(len(socket.sent), 1)
    self.assertTrue(socket.closed)


if __name__ == "__main__":
  unittest.main()
