import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / 'scripts').mkdir()
    shutil.copy(ROOT / 'scripts/dev.sh', tmp_path / 'scripts/dev.sh')
    shutil.copy(ROOT / '.env.example', tmp_path / '.env.example')
    (tmp_path / 'docker-compose.yml').touch()
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    for name in ('docker', 'kubectl', 'helm'):
        p = bindir / name
        p.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$CALLS"
if [[ "$1" == compose && "$*" == *'config --format json'* ]]; then [[ "${PROJECT_FAIL:-0}" != 1 ]] || exit 1; printf '{"name":"%s"}' "${PROJECT_NAME:-testproject}"; exit 0; fi
if [[ "$1" == volume && "$2" == ls ]]; then [[ "${VOLUME_FAIL:-0}" != 1 ]] || exit 1; if [[ "$*" != *'label=com.docker.compose.project='* || "$*" == *"label=com.docker.compose.project=${VOLUME_PROJECT:-testproject}"* ]]; then printf '%s' "${VOLUMES:-}"; fi; exit 0; fi
if [[ "$1" == install && "${HELM_RELEASES:-[]}" != '[]' ]]; then echo 'cannot re-use a name that is still in use' >&2; exit 1; fi
if [[ "$1" == get && "$2" == secret ]]; then [[ "${SECRET_FAIL:-0}" != 1 ]] || exit 1; [[ "${SECRET_EXISTS:-0}" != 1 ]] || echo secret/existing; exit 0; fi
if [[ "$1" == get && "$2" == pvc ]]; then [[ "${PVC_FAIL:-0}" != 1 ]] || exit 1; printf '%s' "${PVCS:-}"; fi
if [[ "$1" == create && "$2" == -f ]]; then cat > "$CAPTURE"; [[ "${CREATE_FAIL:-0}" != 1 ]] || exit 1; fi
''')
        p.chmod(0o755)
    env = os.environ.copy()
    env.update(PATH=f'{bindir}:' + env['PATH'], CALLS=str(tmp_path / 'calls'), CAPTURE=str(tmp_path / 'secret.json'))
    return tmp_path, env


def run(ws, *args, input=''):
    root, env = ws
    return subprocess.run(['bash', str(root / 'scripts/dev.sh'), *args], input=input, text=True, capture_output=True, env=env)


def test_local_credentials_match_and_are_private(workspace):
    root, _ = workspace
    assert run(workspace, 'env').returncode == 0
    values = dict(line.split('=', 1) for line in (root / '.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
    assert f":{values['POSTGRES_PASSWORD']}@postgres:" in values['DATABASE_URL']
    assert (root / '.env').stat().st_mode & 0o777 == 0o600


def test_config_is_quiet_and_overlay_optional(workspace):
    root, _ = workspace
    (root / 'docker-compose.dev.yml').touch()
    assert run(workspace, 'config').returncode == 0
    calls = (root / 'calls').read_text()
    assert 'docker-compose.dev.yml' in calls and 'config --quiet' in calls


def test_noninteractive_without_command_does_not_deploy(workspace):
    root, _ = workspace
    assert run(workspace).returncode != 0
    assert not (root / 'calls').exists()


def test_prepare_then_cancel_does_not_contact_cluster(workspace):
    root, _ = workspace
    result = run(workspace, input='6\nrelease\nnamespace\ncontext\nn\n0\n')
    assert result.returncode == 0
    assert not (root / 'calls').exists()


def test_local_up_stops_if_credentials_cannot_be_created(workspace):
    root, _ = workspace
    (root / '.env').symlink_to(root / 'missing')
    run(workspace, input='2\n0\n')
    assert not (root / 'calls').exists()


def test_prepare_fails_closed_if_pvc_exists(workspace):
    root, env = workspace
    env['PVCS'] = 'persistentvolumeclaim/data-release-sam-postgresql-0'
    result = run(workspace, input='6\nrelease\nnamespace\ncontext\ny\n0\n')
    assert not (root / 'secret.json').exists()
    assert 'PVC' in result.stdout + result.stderr


def test_existing_kubernetes_credentials_are_never_used_or_overwritten(workspace):
    root, _ = workspace
    path = root / '.env.kubernetes'
    original = 'POSTGRES_PASSWORD=do-not-replace\n'
    path.write_text(original)
    result = run(workspace, input='6\nrelease\nnamespace\ncontext\ny\n0\n')
    assert path.read_text() == original
    assert not (root / 'secret.json').exists()
    assert 'Secret created' not in result.stdout


def test_secret_creation_failure_is_reported_without_deploying(workspace):
    root, env = workspace
    env['CREATE_FAIL'] = '1'
    result = run(workspace, input='6\nrelease\nnamespace\ncontext\ny\n0\n')
    assert result.returncode != 0
    assert 'Secret created' not in result.stdout
    assert 'Secret created' not in result.stderr


def test_prepare_creates_contract_without_secrets_in_arguments(workspace):
    import json
    root, _ = workspace
    result = run(workspace, input='6\nrelease\nnamespace\ncontext\ny\n0\n')
    assert result.returncode == 0
    data = json.loads((root / 'secret.json').read_text())['stringData']
    assert set(data) == {'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB', 'DATABASE_URL', 'REDIS_URL', 'JWT_SECRET', 'AGENT_API_KEY', 'OPENAI_API_KEY'}
    assert f":{data['POSTGRES_PASSWORD']}@release-sam-postgresql:" in data['DATABASE_URL']
    assert data['REDIS_URL'] == 'redis://release-sam-redis:6379/0'
    assert data['POSTGRES_PASSWORD'] not in (root / 'calls').read_text() + result.stdout + result.stderr


@pytest.mark.parametrize('args', [('env',), ('env', '--force'), ('up',)])
def test_existing_compose_volume_prevents_new_password(workspace, args):
    root, env = workspace
    env['VOLUMES'] = 'existing-volume\n'
    result = run(workspace, *args)
    assert result.returncode != 0
    assert not (root / '.env').exists()


def test_volume_query_failure_is_closed(workspace):
    root, env = workspace
    env['VOLUME_FAIL'] = '1'
    assert run(workspace, 'env').returncode != 0
    assert not (root / '.env').exists()


def test_unrelated_pvc_does_not_block_preparation(workspace):
    root, env = workspace
    env['PVCS'] = 'persistentvolumeclaim/data-other-sam-postgresql-0\n'
    assert run(workspace, input='6\nrelease\nnamespace\ncontext\ny\n0\n').returncode == 0
    assert (root / 'secret.json').exists()


@pytest.mark.parametrize('failure', ['SECRET_FAIL', 'PVC_FAIL'])
def test_failed_cluster_reads_abort(workspace, failure):
    root, env = workspace
    env[failure] = '1'
    assert run(workspace, input='6\nrelease\nnamespace\ncontext\ny\n0\n').returncode != 0
    assert not (root / 'secret.json').exists()
    assert not (root / '.env.kubernetes').exists()


def test_retry_after_failed_create_reuses_credentials(workspace):
    root, env = workspace
    env['CREATE_FAIL'] = '1'
    assert run(workspace, input='6\nrelease\nnamespace\ncontext\ny\n0\n').returncode != 0
    before = (root / '.env.kubernetes').read_bytes()
    env['CREATE_FAIL'] = '0'
    result = run(workspace, input='6\nrelease\nnamespace\ncontext\ny\n0\n')
    assert result.returncode == 0
    assert (root / '.env.kubernetes').read_bytes() == before
    assert 'reusing' in result.stdout.lower()


def test_retry_wrong_context_is_refused(workspace):
    root, env = workspace
    env['CREATE_FAIL'] = '1'
    run(workspace, input='6\nrelease\nnamespace\ncontext\ny\n0\n')
    (root / 'secret.json').unlink()
    env['CREATE_FAIL'] = '0'
    assert run(workspace, input='6\nrelease\nnamespace\nother\ny\n0\n').returncode != 0
    assert not (root / 'secret.json').exists()


def test_missing_cluster_inputs_fail(workspace):
    root, _ = workspace
    assert run(workspace, input='7\nrelease\n').returncode != 0
    assert not (root / 'calls').exists()


def test_deploy_cancel_and_exact_target(workspace):
    root, env = workspace
    assert run(workspace, input='7\nrelease\nnamespace\ncontext\nn\n0\n').returncode == 0
    assert not (root / 'calls').exists()
    env['SECRET_EXISTS'] = '1'
    assert run(workspace, input='7\nrelease\nnamespace\ncontext\ny\n0\n').returncode == 0
    calls = (root / 'calls').read_text()
    assert 'get secret release-sam-secrets --context context -n namespace' in calls
    assert '--kube-context context --namespace namespace' in calls


def test_logs_all_with_system_bash(workspace):
    root, env = workspace
    (root / '.env').write_text('existing\n')
    result = subprocess.run(['/bin/bash', str(root / 'scripts/dev.sh')], input='5\n\n0\n', text=True, capture_output=True, env=env)
    assert result.returncode == 0, result.stderr
    assert 'logs -f' in (root / 'calls').read_text()


def test_unrelated_compose_project_does_not_block(workspace):
    root, env = workspace
    env.update(PROJECT_NAME='current', VOLUME_PROJECT='other', VOLUMES='other-volume')
    (root / '.env').write_text('POSTGRES_PASSWORD=old\n')
    assert run(workspace, 'env', '--force').returncode == 0
    assert (root / '.env').exists()
    assert 'label=com.docker.compose.project=current' in (root / 'calls').read_text()


def test_matching_compose_project_blocks(workspace):
    root, env = workspace
    env.update(PROJECT_NAME='custom', VOLUME_PROJECT='custom', VOLUMES='own-volume')
    path = root / '.env'
    path.write_text('POSTGRES_PASSWORD=old\n')
    assert run(workspace, 'env', '--force').returncode != 0
    assert path.read_text() == 'POSTGRES_PASSWORD=old\n'


def test_force_does_not_replace_existing_env_with_project_override(workspace):
    root, _ = workspace
    path = root / '.env'
    path.write_text('COMPOSE_PROJECT_NAME=oldproject\nPOSTGRES_PASSWORD=old\n')
    assert run(workspace, 'env', '--force').returncode != 0
    assert path.read_text() == 'COMPOSE_PROJECT_NAME=oldproject\nPOSTGRES_PASSWORD=old\n'


def test_ambiguous_compose_project_blocks(workspace):
    root, env = workspace
    env['PROJECT_FAIL'] = '1'
    path = root / '.env'
    path.write_text('POSTGRES_PASSWORD=old\n')
    assert run(workspace, 'env', '--force').returncode != 0
    assert path.read_text() == 'POSTGRES_PASSWORD=old\n'


def test_help_documents_manual_pvc_recovery(workspace):
    result = run(workspace, 'help')
    assert 'restore' in result.stdout.lower()
    assert 'original secret' in result.stdout.lower()
    assert 'without' in result.stdout.lower()


def test_deploy_forces_standard_names_and_resets_previous_values(workspace):
    root, env = workspace
    env['SECRET_EXISTS'] = '1'
    assert run(workspace, input='7\nrelease\nnamespace\ncontext\ny\n0\n').returncode == 0
    calls = (root / 'calls').read_text()
    assert '--reset-values' not in calls
    assert 'upgrade --install' not in calls
    assert 'install release ' in calls
    assert '--set-string nameOverride=sam,fullnameOverride=release-sam' in calls


def test_force_rotates_only_after_volume_check_and_warns(workspace):
    root, env = workspace
    env['VOLUMES'] = ''
    first = run(workspace, 'env')
    assert first.returncode == 0
    old = (root / '.env').read_bytes()
    result = run(workspace, 'env', '--force')
    assert result.returncode == 0
    assert (root / '.env').read_bytes() != old
    assert 'rotat' in (result.stdout + result.stderr).lower()


def test_missing_env_with_any_postgres_volume_fails_closed(workspace):
    root, env = workspace
    env.update(PROJECT_FAIL='0', VOLUME_PROJECT='', VOLUMES='orphan-volume')
    result = run(workspace, 'env')
    assert result.returncode != 0
    assert not (root / '.env').exists()
    assert 'volume' in result.stderr.lower()


def test_existing_env_filters_current_project_volume(workspace):
    root, env = workspace
    (root / '.env').write_text('COMPOSE_PROJECT_NAME=current\nPOSTGRES_PASSWORD=old\n')
    env.update(VOLUME_PROJECT='other', VOLUMES='other-volume')
    result = run(workspace, 'env', '--force')
    assert result.returncode != 0
    assert (root / '.env').read_text().startswith('COMPOSE_PROJECT_NAME=current')


def test_existing_release_is_not_upgraded(workspace):
    root, env = workspace
    env['HELM_RELEASES'] = '[{"name":"release","namespace":"namespace"}]'
    result = run(workspace, input='7\nrelease\nnamespace\ncontext\ny\n0\n')
    assert result.returncode != 0
    calls = (root / 'calls').read_text()
    assert 'upgrade --install' not in calls
    assert '--reset-values' not in calls
