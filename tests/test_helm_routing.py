import re
import subprocess
from pathlib import Path

import pytest


CHART = Path(__file__).resolve().parents[1] / "deploy/helm/sam"


def render(*args):
    result = subprocess.run(
        ["helm", "template", "demo", str(CHART), "--set", "existingSecret=test-secret", *args],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.split("\n---\n")


def resource(documents, kind, name):
    return next(doc for doc in documents if f"kind: {kind}\n" in doc and re.search(rf"(?m)^  name: {re.escape(name)}$", doc))


@pytest.mark.parametrize("overrides,prefix", [
    ([], "demo-sam"),
    (["--set", "fullnameOverride=custom"], "custom"),
    (["--set", "nameOverride=other"], "demo-other"),
])
def test_web_proxy_uses_release_services_and_strips_prefixes(overrides, prefix):
    docs = render(*overrides, "--set", "services.api.port=9000", "--set", "services.ingest.port=9001")
    web = resource(docs, "Deployment", f"{prefix}-web")
    assert "mountPath: /etc/nginx/conf.d/default.conf" in web
    assert "subPath: default.conf" in web
    assert f"name: {prefix}-web-nginx" in web
    config = resource(docs, "ConfigMap", f"{prefix}-web-nginx")
    for route, port in (("api", 9000), ("ingest", 9001)):
        assert re.search(rf"location /{route}/\s*\{{\s*proxy_pass http://{prefix}-{route}:{port}/;", config)
    assert "location = /healthz" in config
    assert "try_files $uri $uri/ /index.html;" in config


def test_web_rolls_out_when_proxy_configuration_changes():
    default = resource(render(), "Deployment", "demo-sam-web")
    changed = resource(render("--set", "services.api.port=9000"), "Deployment", "demo-sam-web")
    checksum = r"checksum/web-nginx: ([a-f0-9]{64})"
    assert re.search(checksum, default)
    assert re.search(checksum, changed)
    assert re.search(checksum, default).group(1) != re.search(checksum, changed).group(1)


def test_ingress_requires_web_service():
    result = subprocess.run(
        ["helm", "template", "demo", str(CHART), "--set", "existingSecret=test-secret",
         "--set", "ingress.enabled=true", "--set", "services.web.enabled=false"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "ingress.enabled requires services.web.enabled" in result.stderr


@pytest.mark.parametrize("service", ["api", "ingest"])
def test_disabled_upstream_returns_503_without_resolving_service(service):
    docs = render("--set", f"services.{service}.enabled=false")
    config = resource(docs, "ConfigMap", "demo-sam-web-nginx")
    assert f"http://demo-sam-{service}:" not in config
    assert re.search(rf"location /{service}/\s*\{{\s*return 503;", config)


@pytest.mark.parametrize("route", ["api", "ingest"])
def test_prefix_without_slash_does_not_return_spa(route):
    config = resource(render(), "ConfigMap", "demo-sam-web-nginx")
    assert re.search(rf"location = /{route}\s*\{{\s*return 404;", config)


def test_custom_backend_port_and_command_are_rendered_together():
    docs = render("--set", "services.api.port=9000", "--set-string", "services.api.command={uvicorn,app.api:app,--host,0.0.0.0,--port,9000}")
    api = resource(docs, "Deployment", "demo-sam-api")
    assert re.search(r"containerPort: 9000", api)
    assert re.search(r"- --port\s*\n\s*- \"?9000\"?", api)
    service = resource(docs, "Service", "demo-sam-api")
    assert "port: 9000" in service


def test_ingress_sends_all_routes_through_web_proxy():
    docs = render("--set", "ingress.enabled=true", "--set", "fullnameOverride=custom")
    ingress = resource(docs, "Ingress", "custom")
    assert "path: /" in ingress
    assert re.findall(r"name: (custom-(?:web|api|ingest))", ingress) == ["custom-web"]
