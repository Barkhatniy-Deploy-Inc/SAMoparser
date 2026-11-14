import os
import subprocess
import tempfile
from pathlib import Path


CHART = Path(__file__).resolve().parents[1] / "deploy/helm/sam"


def render(*args):
    return subprocess.run(
        ["helm", "template", "demo", str(CHART), "--set", "existingSecret=test-secret", *args],
        check=True, capture_output=True, text=True,
    ).stdout


def test_external_dependencies_remain_default():
    result = render()
    assert "kind: StatefulSet" not in result
    assert "name: demo-sam-postgresql" not in result
    assert "name: demo-sam-redis" not in result
    assert 'key: "DATABASE_URL"' in result
    assert 'key: "REDIS_URL"' in result


def test_hackathon_uses_external_postgresql_and_persistent_redis():
    result = render("-f", str(CHART / "values-hackathon.yaml"))
    assert "demo-sam-postgresql" not in result
    assert result.count("kind: StatefulSet") == 1
    assert "name: demo-sam-redis" in result
    assert "serviceName: demo-sam-redis" in result
    assert "volumeClaimTemplates:" in result
    assert "whenDeleted: Retain" in result
    assert "whenScaled: Retain" in result
    assert '"--appendonly"' in result and '"yes"' in result
    for setting in ('DB_HOST: "37.139.42.15"', 'DB_PORT: "5432"',
                    'DB_USER: "sam_app"', 'DB_SSLMODE: "require"',
                    'REDIS_HOST: "demo-sam-redis"', 'REDIS_PORT: "6379"'):
        assert setting in result
    assert "name: demo-sam-worker" not in result
    assert "name: demo-sam-migration" not in result


def test_opt_in_postgresql_initialization():
    result = render("--set", "postgresql.enabled=true")
    assert "name: demo-sam-postgresql" in result
    assert "CREATE EXTENSION IF NOT EXISTS vector" in result
    assert "/docker-entrypoint-initdb.d" in result
    for key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        assert f"key: {key}" in result


def test_postgresql_readiness_uses_authenticated_tcp_and_checks_vector():
    result = render("-f", str(CHART / "values-hackathon.yaml"), "--set", "postgresql.enabled=true")
    postgres = result.split("kind: StatefulSet\nmetadata:\n  name: demo-sam-postgresql", 1)[1].split("\n---", 1)[0]
    probe = postgres.split("readinessProbe:", 1)[1].split("volumeMounts:", 1)[0]
    lines = probe.splitlines()
    assert "- sh" in probe and "- -c" in probe
    script = "\n".join(line.strip() for line in lines if line.strip().startswith(("export ", "result=", "[ ")))
    command = ["sh", "-c", script]
    with tempfile.TemporaryDirectory() as directory:
        fake = Path(directory) / "psql"
        fake.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$ARGS_FILE"\n[ "$PGPASSWORD" = "$EXPECTED_PASSWORD" ] || exit 1\nprintf "%s\\n" "$PSQL_RESULT"\n')
        fake.chmod(0o755)
        env = dict(os.environ, PATH=directory + os.pathsep + os.environ["PATH"],
                   ARGS_FILE=str(Path(directory) / "args"), POSTGRES_USER="sam",
                   POSTGRES_PASSWORD="secret", POSTGRES_DB="samdb", EXPECTED_PASSWORD="secret")
        for output, expected in (("1", 0), ("0", 1), ("", 1)):
            process = subprocess.run(command, env=dict(env, PSQL_RESULT=output), capture_output=True)
            assert (process.returncode == 0) == (expected == 0)
        assert subprocess.run(command, env=dict(env, PSQL_RESULT="1", EXPECTED_PASSWORD="wrong"), capture_output=True).returncode != 0
        args = (Path(directory) / "args").read_text()
        assert "127.0.0.1" in args
        assert "pg_extension" in args and "vector" in args
        assert "secret" not in args
    assert "livenessProbe:" not in postgres


def test_ssl_mode_is_internal_only_when_postgresql_enabled():
    assert 'DB_SSLMODE: "disable"' in render("--set", "postgresql.enabled=true")
    assert 'DB_SSLMODE: "require"' in render()
    assert 'DB_SSLMODE: "verify-full"' in render("--set", "database.sslMode=verify-full")
    assert 'DB_SSLMODE: "verify-full"' in render("-f", str(CHART / "values-hackathon.yaml"), "--set", "postgresql.enabled=false", "--set", "database.sslMode=verify-full")


def test_connection_settings_follow_each_dependency_mode():
    overrides = ("--set", "database.port=15432", "--set", "redis.port=16379", "--set", "database.user=external-user")
    for pg, redis, db_port, redis_port in ((False, False, 15432, 16379), (True, True, 5432, 6379), (True, False, 5432, 16379), (False, True, 15432, 6379)):
        result = render(*overrides, "--set", f"postgresql.enabled={str(pg).lower()}", "--set", f"redis.enabled={str(redis).lower()}")
        config = result.split("name: demo-sam-config\n", 1)[1].split("\n---", 1)[0]
        assert f'DB_PORT: "{db_port}"' in config
        assert f'REDIS_PORT: "{redis_port}"' in config
        workloads = [doc for doc in result.split("\n---") if "kind: Deployment" in doc and "name: demo-sam-web\n" not in doc]
        assert workloads
        if pg:
            assert "DB_USER:" not in config
            for workload in workloads:
                assert '- name: DB_USER\n              valueFrom:\n                secretKeyRef:\n                  name: "test-secret"\n                  key: POSTGRES_USER' in workload
        else:
            assert 'DB_USER: "external-user"' in config
            assert all('- name: DB_USER' not in workload for workload in workloads)


def test_stateful_storage_is_configurable_and_components_independent():
    result = render("-f", str(CHART / "values-hackathon.yaml"), "--set", "postgresql.enabled=true", "--set", "postgresql.persistence.storageClass=fast", "--set", "postgresql.persistence.size=12Gi", "--set", "redis.enabled=false")
    assert "name: demo-sam-postgresql" in result
    assert "name: demo-sam-redis" not in result
    assert 'storageClassName: "fast"' in result
    assert "storage: 12Gi" in result
