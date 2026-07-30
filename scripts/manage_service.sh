#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
XRT_UNIT="xrobotoolkit-pc.service"
PUBLISHER_UNIT="xrobot-vr-input.service"
XRT_SCRIPT="$SCRIPT_DIR/start_xrt_service.sh"
XRT_SERVICE_DIR="${XROBOTOOLKIT_PC_SERVICE_DIR:-/opt/apps/roboticsservice}"
VENV_BIN="$PROJECT_ROOT/.venv/bin"

install_units() {
  if [[ ! -x "$VENV_BIN/xrobot-vr-publisher" ]]; then
    echo "Missing $VENV_BIN/xrobot-vr-publisher" >&2
    echo "Run: uv sync --project $PROJECT_ROOT --extra service --no-editable" >&2
    exit 1
  fi
  if ! "$VENV_BIN/python" -c "import xrobotoolkit_sdk" 2>/dev/null; then
    echo "Missing xrobottoolkit_sdk in $VENV_BIN" >&2
    echo "Run: uv sync --project $PROJECT_ROOT --extra service --no-editable" >&2
    exit 1
  fi
  mkdir -p "$UNIT_DIR"
  sed \
    -e "s|@PROJECT_ROOT@|$PROJECT_ROOT|g" \
    -e "s|@XRT_SERVICE_DIR@|$XRT_SERVICE_DIR|g" \
    -e "s|@XRT_SCRIPT@|$XRT_SCRIPT|g" \
    "$PROJECT_ROOT/systemd/$XRT_UNIT" > "$UNIT_DIR/$XRT_UNIT"
  sed \
    -e "s|@PROJECT_ROOT@|$PROJECT_ROOT|g" \
    -e "s|@VENV_BIN@|$VENV_BIN|g" \
    "$PROJECT_ROOT/systemd/$PUBLISHER_UNIT" > "$UNIT_DIR/$PUBLISHER_UNIT"

  systemctl --user daemon-reload
  echo "[vr-service] installed units from $PROJECT_ROOT"
}

publisher_port_in_use() {
  ss -ltn 2>/dev/null | grep -qE '(^|[[:space:]])[^[:space:]]*:5592[[:space:]]'
}

prepare_start() {
  if ! systemctl --user is-active --quiet "$PUBLISHER_UNIT" \
    && publisher_port_in_use; then
    echo "[vr-service] tcp://*:5592 is already in use by a manual publisher." >&2
    echo "Stop that publisher with Ctrl-C, then run this command again." >&2
    exit 1
  fi
  if ! systemctl --user is-active --quiet "$XRT_UNIT" \
    && [[ -n "$(pgrep -f '^./RoboticsServiceProcess$' 2>/dev/null || true)$(pgrep -x RoboticsService 2>/dev/null || true)" ]]; then
    echo "[vr-service] stopping the unmanaged XRoboToolkit service"
    bash "$XRT_SCRIPT" stop
  fi
}

start_services() {
  install_units
  prepare_start
  systemctl --user start "$PUBLISHER_UNIT"
  systemctl --user --no-pager --full status "$XRT_UNIT" "$PUBLISHER_UNIT"
}

stop_services() {
  systemctl --user stop "$PUBLISHER_UNIT" "$XRT_UNIT"
  echo "[vr-service] stopped $PUBLISHER_UNIT and $XRT_UNIT"
}

health_services() {
  local failed=0
  for unit in "$XRT_UNIT" "$PUBLISHER_UNIT"; do
    if systemctl --user is-active --quiet "$unit"; then
      echo "[vr-health] $unit active"
    else
      echo "[vr-health] $unit inactive" >&2
      failed=1
    fi
  done
  for port in 60061 63901 5592; do
    if ss -ltn 2>/dev/null | grep -qE ":$port([[:space:]]|$)"; then
      echo "[vr-health] tcp:$port listening"
    else
      echo "[vr-health] tcp:$port not listening" >&2
      failed=1
    fi
  done
  if ! "$VENV_BIN/xrobot-vr-health"; then
    failed=1
  fi
  return "$failed"
}

case "$ACTION" in
  install)
    install_units
    ;;
  start)
    start_services
    ;;
  stop)
    stop_services
    ;;
  restart)
    stop_services
    start_services
    ;;
  status)
    systemctl --user --no-pager --full status "$XRT_UNIT" "$PUBLISHER_UNIT" || true
    ;;
  health)
    health_services
    ;;
  logs)
    journalctl --user -u "$XRT_UNIT" -u "$PUBLISHER_UNIT" -f
    ;;
  enable)
    install_units
    prepare_start
    systemctl --user enable --now "$XRT_UNIT" "$PUBLISHER_UNIT"
    ;;
  disable)
    systemctl --user disable --now "$PUBLISHER_UNIT" "$XRT_UNIT"
    ;;
  *)
    echo "Usage: $0 [install|start|stop|restart|status|health|logs|enable|disable]" >&2
    exit 2
    ;;
esac
