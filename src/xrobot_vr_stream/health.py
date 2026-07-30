"""Check the live published VR stream."""

from __future__ import annotations

import argparse
import time

from xrobot_vr_stream.subscriber import DEFAULT_VR_CONNECT, VrSubscriber


def main() -> None:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--connect", default=DEFAULT_VR_CONNECT)
  parser.add_argument("--timeout-s", type=float, default=2.0)
  args = parser.parse_args()
  subscriber = VrSubscriber(
    connect=args.connect,
    stale_after_s=args.timeout_s,
    start_local_service=False,
  )
  subscriber.start()
  deadline = time.monotonic() + args.timeout_s
  try:
    while time.monotonic() < deadline:
      frame = subscriber.poll()
      if frame.source_status != "transport_stale":
        age_ms = max(0, time.time_ns() - frame.publish_timestamp_ns) / 1e6
        print(
          f"[vr-health] session={frame.session_id} sequence={frame.sequence} "
          f"status={frame.source_status} body={bool(frame.body.available)} "
          f"age_ms={age_ms:.1f}"
        )
        return
      time.sleep(0.01)
  finally:
    subscriber.stop()
  raise SystemExit(f"no VR frame received from {args.connect}")


if __name__ == "__main__":
  main()
