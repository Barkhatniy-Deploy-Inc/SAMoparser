#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_EXAMPLE="${ROOT_DIR}/.env.example"
ENV_FILE="${ROOT_DIR}/.env"
COMPOSE=(docker compose --project-directory "${ROOT_DIR}")

usage() {
  cat <<'EOF'
Usage: ./scripts/dev.sh <command> [options]

Commands:
  env [--force]       Create .env from .env.example with random local secrets
  up [service ...]    Build and start the local stack in background
  down               Stop and remove local containers
  restart             Restart the local stack
  logs [service ...]  Follow logs; optionally limit to services
  status              Show container status
  config              Validate and print the resolved Compose configuration
  help                Show this help

Examples:
  ./scripts/dev.sh env
  ./scripts/dev.sh up
  ./scripts/dev.sh logs api worker
  ./scripts/dev.sh down
EOF
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Error: '$1' is required but was not found in PATH." >&2
    exit 1
  }
}

random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(32))'
  else
    echo "Error: openssl or python3 is required to generate secrets." >&2
    exit 1
  fi
}

ensure_example() {
  [[ -f "${ENV_EXAMPLE}" ]] || {
    echo "Error: ${ENV_EXAMPLE} does not exist." >&2
    exit 1
  }
}

generate_env() {
  local force="${1:-false}"
  ensure_example

  if [[ -e "${ENV_FILE}" && "${force}" != "true" ]]; then
    echo "${ENV_FILE} already exists; refusing to overwrite it."
    echo "Use '$0 env --force' only if you intend to rotate local secrets."
    return 0
  fi

  umask 077
  sed \
    -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(random_secret)/" \
    -e "s/^JWT_SECRET=.*/JWT_SECRET=$(random_secret)/" \
    -e "s/^AGENT_API_KEY=.*/AGENT_API_KEY=$(random_secret)/" \
    "${ENV_EXAMPLE}" > "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"

  echo "Created ${ENV_FILE} with random local secrets."
  echo "This file is ignored by Git and must not be used for production."
}

require_env() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "${ENV_FILE} is missing; generating it first."
    generate_env
  fi
}

main() {
  local command="${1:-help}"
  shift || true

  case "${command}" in
    env)
      [[ "${1:-}" == "--force" ]] && generate_env true || generate_env
      ;;
    up)
      require_command docker
      require_env
      "${COMPOSE[@]}" up --build -d "$@"
      echo
      echo "Local stack is starting. Web UI: http://localhost:8080"
      ;;
    down)
      require_command docker
      "${COMPOSE[@]}" down "$@"
      ;;
    restart)
      require_command docker
      require_env
      "${COMPOSE[@]}" restart "$@"
      ;;
    logs)
      require_command docker
      require_env
      "${COMPOSE[@]}" logs -f "$@"
      ;;
    status)
      require_command docker
      "${COMPOSE[@]}" ps
      ;;
    config)
      require_command docker
      require_env
      "${COMPOSE[@]}" config
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      echo "Unknown command: ${command}" >&2
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
