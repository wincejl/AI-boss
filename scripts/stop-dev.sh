#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/.dev/pids.tsv"
STOP_INFRA=0
STOP_MILVUS=0

usage() {
  cat <<'EOF'
Usage: ./scripts/stop-dev.sh [--infra] [--milvus]

Options:
  --infra   Also stop the MySQL Docker service.
  --milvus  Also stop Milvus Docker services.
  -h, --help  Show this help message.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --infra)
      STOP_INFRA=1
      shift
      ;;
    --milvus)
      STOP_MILVUS=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

stop_tree() {
  local pid="$1"

  if ! kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi

  local children
  children="$(pgrep -P "$pid" 2>/dev/null || true)"
  if [[ -n "$children" ]]; then
    local child
    for child in $children; do
      stop_tree "$child"
    done
  fi

  kill "$pid" >/dev/null 2>&1 || true
  sleep 1
  kill -9 "$pid" >/dev/null 2>&1 || true
}

stop_port() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return 0
  fi

  local pid
  for pid in $pids; do
    stop_tree "$pid"
    echo "Stopped process on port $port pid=$pid"
  done
}

if [[ ! -f "$PID_FILE" ]]; then
  echo "No dev PID file found."
else
  while IFS=$'\t' read -r name pid stdout stderr; do
    if [[ -n "${pid:-}" ]]; then
      stop_tree "$pid"
      echo "Stopped $name pid=$pid"
    fi
  done < "$PID_FILE"

  rm -f "$PID_FILE"
fi

stop_port 8080
stop_port 3000
stop_port 8090

if [[ "$STOP_INFRA" -eq 1 ]]; then
  docker compose stop mysql
fi

if [[ "$STOP_MILVUS" -eq 1 ]]; then
  docker compose -f docker-compose.milvus.yml stop
fi

echo "AIHR dev services stopped."
