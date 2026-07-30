"""Start the installed local VR publisher service on demand."""

from __future__ import annotations

import subprocess


LOCAL_VR_CONNECT = "tcp://127.0.0.1:5592"
PUBLISHER_UNIT = "xrobot-vr-input.service"


def ensure_local_service(connect: str) -> None:
  if str(connect) != LOCAL_VR_CONNECT:
    return
  active = subprocess.run(
    ["systemctl", "--user", "is-active", "--quiet", PUBLISHER_UNIT],
    check=False,
  )
  if active.returncode == 0:
    return
  started = subprocess.run(
    ["systemctl", "--user", "start", PUBLISHER_UNIT],
    check=False,
    capture_output=True,
    text=True,
  )
  if started.returncode != 0:
    detail = started.stderr.strip() or started.stdout.strip()
    raise RuntimeError(
      f"could not start {PUBLISHER_UNIT}: {detail}; "
      "install it once with xrobot_vr_stream/scripts/manage_service.sh install"
    )
