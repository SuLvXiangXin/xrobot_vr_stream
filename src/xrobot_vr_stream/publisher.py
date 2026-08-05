"""Publish one complete VR frame stream from the single XR input client."""

from __future__ import annotations

import argparse
from dataclasses import replace
import time
import uuid

import zmq

from xrobot_vr_stream._xrt import XrtFrameSource
from xrobot_vr_stream.protocol import (
  empty_vr_frame,
  pack_vr_frame,
)
from xrobot_vr_stream.synthetic import SyntheticFrameSource


def main() -> None:
  args = _parse_args()
  if args.fps <= 0.0:
    raise ValueError("--fps must be positive")
  if args.frames < 0:
    raise ValueError("--frames must be non-negative")
  socket = _publisher_socket(args.bind)
  source = None

  print(f"[vr-input] source={args.source} bind={args.bind} fps={args.fps:g}")
  frame_count = 0
  sequence = 0
  session_id = uuid.uuid4().hex
  retry_delay_s = 1.0
  next_deadline = time.monotonic()
  try:
    while args.frames == 0 or frame_count < args.frames:
      try:
        if source is None:
          source = (
            XrtFrameSource(start_service=args.start_service)
            if args.source == "xrt"
            else SyntheticFrameSource(fps=args.fps)
          )
          source.start()
        frame = source.read()
        retry_delay_s = 1.0
      except Exception as exc:
        print(
          f"[vr-input] XRT unavailable: {exc}; "
          f"retrying in {retry_delay_s:g}s",
          flush=True,
        )
        if source is not None:
          try:
            source.close()
          except Exception as close_exc:
            print(f"[vr-input] XRT close failed: {close_exc}", flush=True)
        source = None
        sequence = _send_retry_heartbeats(
          socket,
          session_id=session_id,
          sequence=sequence,
          error=str(exc),
          duration_s=retry_delay_s,
        )
        retry_delay_s = min(2.0 * retry_delay_s, 5.0)
        next_deadline = time.monotonic()
        continue
      status = "connected" if bool(frame.body.available) else "tracking_unavailable"
      frame = replace(
        frame,
        session_id=session_id,
        sequence=sequence,
        publish_timestamp_ns=time.time_ns(),
        source_status=status,
        source_error=None,
      )
      socket.send(pack_vr_frame(frame))
      sequence += 1
      frame_count += 1
      if frame_count == 1 or frame_count % 30 == 0:
        print(
          f"[vr-input] frame={frame_count} "
          f"body_available={bool(frame.body.available)}"
        )
      next_deadline += 1.0 / args.fps
      sleep_s = next_deadline - time.monotonic()
      if sleep_s > 0.0:
        time.sleep(sleep_s)
      else:
        next_deadline = time.monotonic()
  except KeyboardInterrupt:
    print("[vr-input] stopped")
  finally:
    socket.close(0)
    if source is not None:
      try:
        source.close()
      except Exception as exc:
        print(f"[vr-input] XRT close failed: {exc}", flush=True)


def _send_retry_heartbeats(
  socket: zmq.Socket,
  *,
  session_id: str,
  sequence: int,
  error: str,
  duration_s: float,
) -> int:
  deadline = time.monotonic() + duration_s
  while True:
    frame = replace(
      empty_vr_frame(
        source_status="reconnecting",
        source_error=error,
      ),
      session_id=session_id,
      sequence=sequence,
      publish_timestamp_ns=time.time_ns(),
    )
    socket.send(pack_vr_frame(frame))
    sequence += 1
    remaining_s = deadline - time.monotonic()
    if remaining_s <= 0.0:
      return sequence
    time.sleep(min(0.2, remaining_s))


def _publisher_socket(bind: str) -> zmq.Socket:
  socket = zmq.Context.instance().socket(zmq.PUB)
  socket.setsockopt(zmq.LINGER, 0)
  socket.setsockopt(zmq.SNDHWM, 1)
  socket.setsockopt(zmq.CONFLATE, 1)
  socket.bind(str(bind))
  return socket


def _parse_args() -> argparse.Namespace:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--source", choices=("xrt", "synthetic"), default="xrt")
  parser.add_argument("--bind", default="tcp://*:5592")
  parser.add_argument("--fps", type=float, default=30.0)
  parser.add_argument("--frames", type=int, default=0)
  parser.add_argument(
    "--start-service",
    action=argparse.BooleanOptionalAction,
    default=True,
  )
  return parser.parse_args()


if __name__ == "__main__":
  main()
