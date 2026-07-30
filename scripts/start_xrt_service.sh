#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-start}"
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

SERVICE_DIR="${XROBOTOOLKIT_PC_SERVICE_DIR:-/opt/apps/roboticsservice}"
LOG_FILE="${XROBOTOOLKIT_PC_SERVICE_LOG:-$PROJECT_ROOT/.tmp/xrt_service/roboticsservice.log}"
PID_FILE="${XROBOTOOLKIT_PC_SERVICE_PID:-$PROJECT_ROOT/.tmp/xrt_service/roboticsservice.pid}"
mkdir -p "$(dirname "$LOG_FILE")"

case "$(uname -m)" in
  aarch64|arm64) SDK_ARCH="aarch64" ;;
  x86_64|amd64) SDK_ARCH="x64" ;;
  *) SDK_ARCH="$(uname -m)" ;;
esac

SDK_DIR="${XROBOTOOLKIT_SDK_DIR:-$SERVICE_DIR/SDK/$SDK_ARCH}"
QT_LIB_DIR="$SERVICE_DIR/lib"
QT_PLUGINS_DIR="$SERVICE_DIR/plugins"
QT_QML_DIR="$SERVICE_DIR/qml"

service_pids() {
  {
    pgrep -f '^./RoboticsServiceProcess$' 2>/dev/null || true
    pgrep -x RoboticsService 2>/dev/null || true
  } | sort -u
}

service_healthy() {
  [[ -n "$(service_pids)" ]] \
    && ss -ltn 2>/dev/null | grep -q ':60061' \
    && ss -ltn 2>/dev/null | grep -q ':63901'
}

show_status() {
  local pids
  pids="$(service_pids)"
  if [[ -n "$pids" ]]; then
    ps -p "${pids//$'\n'/,}" -o pid,etime,stat,cmd || true
  else
    echo "RoboticsServiceProcess is not running"
  fi
  ss -tlnp 2>/dev/null | grep -E '60061|63901' || true
}

start_service() {
  if [[ -n "$(service_pids)" ]]; then
    if service_healthy; then
      echo "[XRT] RoboticsServiceProcess is already running."
      show_status
      return 0
    fi
    echo "[XRT] Existing service is unhealthy; restarting it."
    stop_service
  fi

  if [[ ! -x "$SERVICE_DIR/RoboticsServiceProcess" ]]; then
    echo "Missing executable: $SERVICE_DIR/RoboticsServiceProcess" >&2
    echo "Set XROBOTOOLKIT_PC_SERVICE_DIR if XRoboToolkit is installed elsewhere." >&2
    exit 1
  fi

  echo "[XRT] Starting service from: $SERVICE_DIR"
  setsid env \
    --chdir="$SERVICE_DIR" \
    -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    -u http_proxy -u https_proxy -u all_proxy \
    -u NO_PROXY -u no_proxy \
    LD_LIBRARY_PATH="$SERVICE_DIR:$QT_LIB_DIR:$SDK_DIR:${LD_LIBRARY_PATH:-}" \
    QT_PLUGIN_PATH="$QT_PLUGINS_DIR:${QT_PLUGIN_PATH:-}" \
    QT_QML_PATH="$QT_QML_DIR:${QT_QML_PATH:-}" \
    QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}" \
    ./RoboticsServiceProcess \
    < /dev/null >> "$LOG_FILE" 2>&1 &
  echo "$!" > "$PID_FILE"

  for _ in $(seq 1 30); do
    if service_healthy; then
      echo "[XRT] RoboticsServiceProcess started."
      show_status
      echo "[XRT] Log: $LOG_FILE"
      return 0
    fi
    sleep 0.25
  done

  echo "[XRT] Failed to start a healthy RoboticsServiceProcess." >&2
  echo "[XRT] Expected gRPC 60061 and PICO TCP 63901 to be listening." >&2
  echo "[XRT] Log: $LOG_FILE" >&2
  [[ -f "$LOG_FILE" ]] && tail -n 120 "$LOG_FILE" >&2
  exit 1
}

run_service() {
  if [[ ! -x "$SERVICE_DIR/RoboticsServiceProcess" ]]; then
    echo "Missing executable: $SERVICE_DIR/RoboticsServiceProcess" >&2
    echo "Set XROBOTOOLKIT_PC_SERVICE_DIR if XRoboToolkit is installed elsewhere." >&2
    exit 1
  fi
  if [[ -n "$(service_pids)" ]]; then
    echo "[XRT] Refusing to start a second RoboticsServiceProcess." >&2
    show_status >&2
    exit 1
  fi
  echo "[XRT] Running service in foreground from: $SERVICE_DIR"
  exec env \
    --chdir="$SERVICE_DIR" \
    -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    -u http_proxy -u https_proxy -u all_proxy \
    -u NO_PROXY -u no_proxy \
    LD_LIBRARY_PATH="$SERVICE_DIR:$QT_LIB_DIR:$SDK_DIR:${LD_LIBRARY_PATH:-}" \
    QT_PLUGIN_PATH="$QT_PLUGINS_DIR:${QT_PLUGIN_PATH:-}" \
    QT_QML_PATH="$QT_QML_DIR:${QT_QML_PATH:-}" \
    QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}" \
    ./RoboticsServiceProcess
}

stop_service() {
  local pids
  pids="$(service_pids)"
  if [[ -z "$pids" ]]; then
    echo "[XRT] RoboticsServiceProcess is not running."
    return 0
  fi
  while read -r pid; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done <<< "$pids"
  sleep 1
  show_status
}

case "$ACTION" in
  start) start_service ;;
  run) run_service ;;
  stop) stop_service ;;
  restart) stop_service; start_service ;;
  status) show_status ;;
  log) tail -n "${XROBOTOOLKIT_PC_SERVICE_LOG_LINES:-120}" "$LOG_FILE" ;;
  *)
    echo "Usage: $0 [start|run|stop|restart|status|log]" >&2
    exit 2
    ;;
esac
