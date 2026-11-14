#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
KUBE_ENV="$ROOT_DIR/.env.kubernetes"
COMPOSE=(docker compose --project-directory "$ROOT_DIR" -f "$ROOT_DIR/docker-compose.yml")
[[ ! -f "$ROOT_DIR/docker-compose.dev.yml" ]] || COMPOSE+=(-f "$ROOT_DIR/docker-compose.dev.yml")

usage() {
  echo 'Usage: ./scripts/dev.sh {env [--force]|up|down|restart|logs|status|config|help}'
  echo 'Without arguments: interactive local and Kubernetes menu.'
  echo 'config validates with --quiet to avoid exposing resolved secrets (no configuration is printed).'
  echo 'Kubernetes deploy installs new releases only; it never upgrades existing releases.'
  echo 'If a PostgreSQL PVC exists without its Secret, stop deployment and restore the original Secret manually from a trusted backup into the same context and namespace, without rotating credentials; verify the database credentials before deployment.'
}
require_command() { command -v "$1" >/dev/null 2>&1 || { echo "Error: $1 is required" >&2; return 1; }; }

generate_env() {
  local volumes project
  [[ ! -L "$ENV_FILE" ]] || { echo 'Refusing symlink .env.' >&2; return 1; }
  if [[ -e "$ENV_FILE" && "${1:-false}" != true ]]; then
    echo 'Local .env exists; refusing to overwrite it.'
    return 0
  fi
  require_command python3 || return 1
  require_command docker || return 1
  if [[ -f "$ENV_FILE" ]]; then
    project="$("${COMPOSE[@]}" config --format json 2>/dev/null | python3 -c 'import json, re, sys; p=json.load(sys.stdin)["name"]; assert isinstance(p, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", p); print(p)' 2>/dev/null)" || { echo 'Cannot determine Compose project; aborting.' >&2; return 1; }
    volumes="$(docker volume ls -q --filter "label=com.docker.compose.project=$project" --filter 'label=com.docker.compose.volume=postgres-data')" || { echo 'Cannot inspect Docker volumes; aborting.' >&2; return 1; }
  else
    volumes="$(docker volume ls -q --filter 'label=com.docker.compose.volume=postgres-data')" || { echo 'Cannot inspect Docker volumes; aborting.' >&2; return 1; }
  fi
  [[ -z "$volumes" ]] || { echo 'A potential Compose PostgreSQL volume exists; restore its original .env and project name rather than generating new credentials.' >&2; return 1; }
  if [[ -f "$ENV_FILE" ]]; then echo 'Warning: --force rotates local credentials; database volumes do not rotate passwords.' >&2; fi
  python3 - "$ROOT_DIR/.env.example" "$ENV_FILE" "${1:-false}" <<'PY'
import os, secrets, sys
source, target, force = sys.argv[1:]
if os.path.lexists(target) and force != 'true':
    print('Local .env exists; refusing to overwrite it.')
    sys.exit(0)
lines = open(source, encoding='utf-8').read().splitlines()
if force == 'true' and os.path.exists(target):
    with open(target, encoding='utf-8') as existing:
        if any(line.lstrip().startswith(('COMPOSE_', 'export COMPOSE_')) for line in existing):
            print('Cannot safely rotate an .env with Compose overrides; preserve it and recover credentials manually.', file=sys.stderr)
            sys.exit(1)
password = secrets.token_hex(32)
values = {'POSTGRES_PASSWORD': password, 'DATABASE_URL': f'postgresql+psycopg://sam:{password}@postgres:5432/sam', 'JWT_SECRET': secrets.token_hex(32), 'AGENT_API_KEY': secrets.token_hex(32)}
flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if force != 'true' else os.O_TRUNC)
flags |= getattr(os, 'O_NOFOLLOW', 0)
fd = os.open(target, flags, 0o600)
os.fchmod(fd, 0o600)
with os.fdopen(fd, 'w', encoding='utf-8') as out:
    for line in lines:
        key = line.partition('=')[0]
        out.write((key + '=' + values[key] if key in values else line) + '\n')
print('Created local .env (private; do not use in production).')
PY
}
require_env() {
  [[ -f "$ENV_FILE" && ! -L "$ENV_FILE" ]] && return 0
  [[ ! -e "$ENV_FILE" && ! -L "$ENV_FILE" ]] || { echo 'Invalid local .env file.' >&2; return 1; }
  generate_env
}

cluster_inputs() {
  read -r -p 'Release: ' release || return 1
  read -r -p 'Namespace: ' namespace || return 1
  read -r -p 'Kubernetes context: ' context || return 1
  [[ "$release" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ && ${#release} -le 40 && "$namespace" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ && ${#namespace} -le 63 && "$context" =~ ^[a-zA-Z0-9][a-zA-Z0-9._:/@-]*$ ]] || { echo 'Invalid or missing cluster inputs.' >&2; return 1; }
  secret="${release}-sam-secrets"
  printf 'Context: %s  Namespace: %s  Release: %s\n' "$context" "$namespace" "$release"
  read -r -p 'Confirm [y/N]: ' confirm || return 1
  [[ "$confirm" == y || "$confirm" == Y ]] || return 2
}

prepare_kube() {
  local release namespace context secret confirm existing pvcs pvc
  local input_status=0
  cluster_inputs || input_status=$?
  if (( input_status )); then
    if (( input_status == 2 )); then echo 'Cancelled.'; return 0; fi
    echo 'Missing or invalid cluster inputs.' >&2; return 1
  fi
  require_command kubectl || return 1
  require_command python3 || return 1
  existing="$(kubectl get secret "$secret" --context "$context" -n "$namespace" --ignore-not-found -o name)" || { echo 'Cannot check Secret; aborting.' >&2; return 1; }
  [[ -z "$existing" ]] || { echo 'Secret already exists; not overwriting or assuming its credentials match. Verify it manually.' >&2; return 1; }
  pvcs="$(kubectl get pvc --context "$context" -n "$namespace" -o name)" || { echo 'Cannot check PVCs; aborting.' >&2; return 1; }
  while IFS= read -r pvc; do
    [[ -z "$pvc" ]] && continue
    [[ "$pvc" =~ ^persistentvolumeclaim/data-${release}-sam-postgresql-[0-9]+$ ]] && { echo 'PostgreSQL PVC exists without Secret; restore the original Secret and verify credentials.' >&2; return 1; }
  done <<< "$pvcs"
  python3 - "$KUBE_ENV" "$release" "$namespace" "$context" <<'PY' || return 1
import os, secrets, sys
path, release, namespace, context = sys.argv[1:]
if os.path.lexists(path):
    import stat
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, encoding='utf-8') as f:
            info = os.fstat(f.fileno())
            lines = f.read().splitlines()
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid(): raise ValueError()
        if not lines or lines[0] != f'# release={release} namespace={namespace} context={context}': raise ValueError()
        data = {}
        for line in lines[1:]:
            key, sep, value = line.partition('=')
            if not sep or key in data: raise ValueError()
            data[key] = value
        keys = {'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB', 'DATABASE_URL', 'REDIS_URL', 'JWT_SECRET', 'AGENT_API_KEY', 'OPENAI_API_KEY'}
        if data.keys() != keys or any(not data[k] for k in keys - {'OPENAI_API_KEY'}): raise ValueError()
        if data['POSTGRES_USER'] != 'sam' or data['POSTGRES_DB'] != 'sam': raise ValueError()
        if any(c not in '0123456789abcdef' for c in data['POSTGRES_PASSWORD']) or len(data['POSTGRES_PASSWORD']) != 64: raise ValueError()
        if data['DATABASE_URL'] != f"postgresql+psycopg://sam:{data['POSTGRES_PASSWORD']}@{release}-sam-postgresql:5432/sam": raise ValueError()
        if data['REDIS_URL'] != f'redis://{release}-sam-redis:6379/0': raise ValueError()
    except (OSError, ValueError, UnicodeError):
        print('Existing Kubernetes credentials are unsafe, incomplete or for another target; refusing reuse.', file=sys.stderr)
        sys.exit(1)
    print('Reusing existing private Kubernetes credentials; no credentials were rotated.')
    sys.exit(0)
pw = secrets.token_hex(32)
values = {'POSTGRES_USER': 'sam', 'POSTGRES_PASSWORD': pw, 'POSTGRES_DB': 'sam', 'DATABASE_URL': f'postgresql+psycopg://sam:{pw}@{release}-sam-postgresql:5432/sam', 'REDIS_URL': f'redis://{release}-sam-redis:6379/0', 'JWT_SECRET': secrets.token_hex(32), 'AGENT_API_KEY': secrets.token_hex(32), 'OPENAI_API_KEY': ''}
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
with os.fdopen(fd, 'w', encoding='utf-8') as f:
    f.write(f'# release={release} namespace={namespace} context={context}\n')
    for key, value in values.items(): f.write(f'{key}={value}\n')
PY
  python3 - "$KUBE_ENV" "$secret" "$namespace" <<'PY' | kubectl create -f - --context "$context" -n "$namespace" >/dev/null 2>&1 || { echo 'Secret creation failed or its outcome is unknown; credentials retained. Check the target and retry safely.' >&2; return 1; }
import json, sys
path, name, namespace = sys.argv[1:]
keys = {'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB', 'DATABASE_URL', 'REDIS_URL', 'JWT_SECRET', 'AGENT_API_KEY', 'OPENAI_API_KEY'}
data = {}
with open(path, encoding='utf-8') as f:
    for line in f:
        if line.startswith('#'): continue
        key, sep, value = line.rstrip('\n').partition('=')
        if not sep or key not in keys or key in data: raise ValueError('Invalid credentials file')
        data[key] = value
if data.keys() != keys: raise ValueError('Incomplete credentials file')
json.dump({'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': name, 'namespace': namespace}, 'type': 'Opaque', 'stringData': data}, sys.stdout)
PY
  echo 'Secret created; keep the private Kubernetes credentials file safe.'
}

deploy_kube() {
  local release namespace context secret confirm existing
  local input_status=0
  cluster_inputs || input_status=$?
  if (( input_status )); then
    if (( input_status == 2 )); then echo 'Cancelled.'; return 0; fi
    echo 'Missing or invalid cluster inputs.' >&2; return 1
  fi
  require_command kubectl || return 1
  require_command helm || return 1
  existing="$(kubectl get secret "$secret" --context "$context" -n "$namespace" --ignore-not-found -o name)" || { echo 'Cannot check Secret.' >&2; return 1; }
  [[ -n "$existing" ]] || { echo 'Secret missing; prepare first.' >&2; return 1; }
  helm install "$release" "$ROOT_DIR/deploy/helm/sam" --kube-context "$context" --namespace "$namespace" -f "$ROOT_DIR/deploy/helm/sam/values-hackathon.yaml" --set "existingSecret=$secret" --set-string "nameOverride=sam,fullnameOverride=${release}-sam"
}

local_command() {
  local command="$1"; shift
  case "$command" in
    env) if [[ "${1:-}" == --force ]]; then generate_env true; else generate_env; fi ;;
    up) require_command docker && require_env && "${COMPOSE[@]}" up --build -d "$@" ;;
    down) require_command docker && "${COMPOSE[@]}" down "$@" ;;
    restart) require_command docker && require_env && "${COMPOSE[@]}" restart "$@" ;;
    logs) require_command docker && require_env && "${COMPOSE[@]}" logs -f "$@" ;;
    status) require_command docker && "${COMPOSE[@]}" ps ;;
    config) require_command docker && require_env && "${COMPOSE[@]}" config --quiet && echo 'Compose configuration is valid.' ;;
    help|-h|--help) usage ;;
    *) usage >&2; return 2 ;;
  esac
}
menu() {
  local choice="${1:-}" services failed=0
  while :; do
    printf '\n1) Local env  2) Up  3) Stop  4) Status  5) Logs\n6) Prepare Kubernetes Secret  7) Deploy Kubernetes  0) Exit\n'
    if [[ -z "$choice" ]]; then read -r -p 'Choice: ' choice || return "$failed"; fi
    case "$choice" in
      1) local_command env || { echo 'Local env failed.' >&2; failed=1; } ;;
      2) local_command up || { echo 'Local up failed.' >&2; failed=1; } ;;
      3) local_command down || { echo 'Local stop failed.' >&2; failed=1; } ;;
      4) local_command status || { echo 'Local status failed.' >&2; failed=1; } ;;
      5) read -r -p 'Services (blank for all): ' services || return 1; if [[ "$services" =~ [^[:space:]] ]]; then read -r -a selected <<< "$services"; local_command logs "${selected[@]}" || { echo 'Local logs failed.' >&2; failed=1; }; else local_command logs || { echo 'Local logs failed.' >&2; failed=1; }; fi ;;
      6) prepare_kube || { echo 'Kubernetes preparation failed.' >&2; failed=1; } ;;
      7) deploy_kube || { echo 'Kubernetes deployment failed.' >&2; failed=1; } ;;
      0) return "$failed" ;;
      *) echo 'Invalid choice.' >&2; failed=1 ;;
    esac
    choice=''
  done
}
if [[ $# -gt 0 ]]; then local_command "$@"; else
  IFS= read -r -p 'Choice: ' first_choice || { usage >&2; exit 1; }
  menu "$first_choice"
fi
