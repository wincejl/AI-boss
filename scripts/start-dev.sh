#!/usr/bin/env bash
set -euo pipefail

NO_AGENT=0
NO_BROWSER=0
NO_INFRA=0
WITH_MILVUS=0

usage() {
  cat <<'EOF'
Usage: ./scripts/start-dev.sh [--no-agent] [--no-browser] [--no-infra] [--with-milvus]

Options:
  --no-agent     Start only backend and frontend.
  --no-browser   Do not open the login page automatically.
  --no-infra     Do not start Docker infrastructure services.
  --with-milvus  Start Milvus and enable vector store for the backend process.
  -h, --help     Show this help message.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-agent)
      NO_AGENT=1
      shift
      ;;
    --no-browser)
      NO_BROWSER=1
      shift
      ;;
    --no-infra)
      NO_INFRA=1
      shift
      ;;
    --with-milvus)
      WITH_MILVUS=1
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

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
AGENT_DIR="$ROOT_DIR/agent-service"
STATE_DIR="$ROOT_DIR/.dev"
LOG_DIR="$STATE_DIR/logs"
PID_FILE="$STATE_DIR/pids.tsv"
RUN_ID="$(date +"%Y%m%d-%H%M%S")"

mkdir -p "$LOG_DIR"
: > "$PID_FILE"

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name not found. Please install it first." >&2
    exit 1
  fi
}

start_background() {
  local name="$1"
  local work_dir="$2"
  shift 2

  local stdout="$LOG_DIR/$RUN_ID-$name.out.log"
  local stderr="$LOG_DIR/$RUN_ID-$name.err.log"
  local pid_file="$STATE_DIR/$RUN_ID-$name.pid"

  (
    cd "$work_dir"
    nohup "$@" >"$stdout" 2>"$stderr" < /dev/null &
    echo $! > "$pid_file"
  )

  local pid
  pid="$(cat "$pid_file")"
  rm -f "$pid_file"
  printf "%s\t%s\t%s\t%s\n" "$name" "$pid" "$stdout" "$stderr" >> "$PID_FILE"
  echo "Started $name pid=$pid"
}

wait_for_compose_service() {
  local service="$1"
  local timeout_seconds="${2:-90}"
  local elapsed=0

  echo "Waiting for $service to become healthy..."
  while [[ "$elapsed" -lt "$timeout_seconds" ]]; do
    local status
    status="$(docker compose ps "$service" --format json 2>/dev/null | sed -n 's/.*"Health":"\([^"]*\)".*/\1/p' | head -n 1)"
    if [[ "$status" == "healthy" ]]; then
      echo "$service is healthy."
      return 0
    fi

    sleep 2
    elapsed=$((elapsed + 2))
  done

  echo "Timed out waiting for $service to become healthy." >&2
  docker compose ps "$service" >&2 || true
  exit 1
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local timeout_seconds="${3:-60}"
  local elapsed=0

  echo "Waiting for $name..."
  while [[ "$elapsed" -lt "$timeout_seconds" ]]; do
    if [[ "$(curl -sS -o /dev/null -w '%{http_code}' "$url" 2>/dev/null)" != "000" ]]; then
      echo "$name is ready."
      return 0
    fi

    sleep 2
    elapsed=$((elapsed + 2))
  done

  echo "Timed out waiting for $name at $url." >&2
  echo "Check logs in $LOG_DIR" >&2
  exit 1
}

require_command go
require_command npm
require_command curl

if [[ "$NO_INFRA" -eq 0 ]]; then
  require_command docker
  docker compose up -d mysql
  wait_for_compose_service mysql

  if [[ "$WITH_MILVUS" -eq 1 ]]; then
    docker compose -f docker-compose.milvus.yml up -d
  fi
fi

if [[ "$NO_AGENT" -eq 0 ]]; then
  AGENT_PYTHON="$AGENT_DIR/.venv/bin/python"
  if [[ ! -x "$AGENT_PYTHON" ]]; then
    echo "Agent Python venv not found: $AGENT_PYTHON" >&2
    echo "Create it with: cd agent-service && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt" >&2
    exit 1
  fi
fi

if [[ "$WITH_MILVUS" -eq 1 ]]; then
  start_background "backend" "$BACKEND_DIR" env MILVUS_DISABLED=false VECTOR_STORE_DISABLED=false MILVUS_REQUIRED=false go run .
else
  start_background "backend" "$BACKEND_DIR" go run .
fi
wait_for_url "backend" "http://127.0.0.1:8080/api/login" 90

start_background "frontend" "$FRONTEND_DIR" npm run dev
wait_for_url "frontend" "http://127.0.0.1:3000/agent/login" 90

if [[ "$NO_AGENT" -eq 0 ]]; then
  start_background "agent-service" "$AGENT_DIR" "$AGENT_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port 8090
  wait_for_url "agent-service" "http://127.0.0.1:8090/health" 45
fi

if [[ "$NO_BROWSER" -eq 0 ]]; then
  open "http://localhost:3000/agent/login" >/dev/null 2>&1 || true
fi

echo "Started AIHR dev services."
echo "Backend:  http://127.0.0.1:8080"
echo "Frontend: http://localhost:3000/agent/login"
if [[ "$NO_AGENT" -eq 0 ]]; then
  echo "Agent:    http://127.0.0.1:8090/health"
fi
if [[ "$WITH_MILVUS" -eq 1 ]]; then
  echo "Milvus:   127.0.0.1:19530"
fi
echo "Logs:     $LOG_DIR"
echo "Stop:     ./scripts/stop-dev.sh"
