import subprocess
from pathlib import Path

CHART = Path(__file__).resolve().parents[1] / "deploy/helm/sam"


def helm(*args):
    return subprocess.run(["helm", "template", "demo", str(CHART), "--set", "existingSecret=test-secret", *args], check=False, capture_output=True, text=True)


def test_web_has_no_secret_environment_and_backends_keep_secret_refs():
    result = helm("--set", "postgresql.enabled=true")
    assert result.returncode == 0, result.stderr
    deployments = [d for d in result.stdout.split("\n---") if "kind: Deployment" in d]
    web = next(d for d in deployments if "name: demo-sam-web\n" in d)
    assert "secretKeyRef:" not in web
    assert "secretRef:" not in web
    for role in ("api", "ingest", "worker"):
        backend = next(d for d in deployments if f"name: demo-sam-{role}\n" in d)
        for key in ("DATABASE_URL", "REDIS_URL", "JWT_SECRET", "AGENT_API_KEY", "OPENAI_API_KEY"):
            assert f'key: "{key}"' in backend
        assert "key: POSTGRES_USER" in backend


def test_chart_readme_avoids_secret_literals_in_command_arguments():
    readme = (CHART / "README.md").read_text()
    assert "--from-literal" not in readme
    assert "migrations.enabled=true" not in readme
    assert "Prepare Kubernetes Secret" in readme
    assert "values-hackathon.yaml" in readme
    assert "pre-install" in readme and "ConfigMap" in readme


def test_migrations_fail_render_even_with_command_and_are_disabled_by_default():
    default = helm()
    assert default.returncode == 0, default.stderr
    assert "name: demo-sam-migration" not in default.stdout
    for extra in ((), ("--set", "migrations.command[0]=true")):
        result = helm("--set", "migrations.enabled=true", *extra)
        assert result.returncode != 0
        assert "scaffold" in result.stderr and "migrations" in result.stderr
