from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_backend_entrypoints_expose_health_readiness_and_metrics():
    from services.backend.app.api import app as api_app
    from services.backend.app.ingest import app as ingest_app

    for application in (api_app, ingest_app):
        paths = {route.path for route in application.routes}
        assert {"/healthz", "/readyz", "/metrics"} <= paths


def test_backend_has_shared_image_and_pinned_dependencies():
    dockerfile = ROOT / "services/backend/Dockerfile"
    requirements = ROOT / "services/backend/requirements.txt"

    assert dockerfile.exists()
    assert "COPY services/backend" in dockerfile.read_text()
    dependency_lines = [
        line for line in requirements.read_text().splitlines() if line and not line.startswith("#")
    ]
    assert dependency_lines
    assert all("==" in line for line in dependency_lines)


def test_worker_template_exposes_celery_application():
    from services.backend.app.worker import celery_app

    assert celery_app.main == "samoparser"


def test_web_and_agent_templates_exist():
    web = ROOT / "services/web"
    agent = ROOT / "services/agent"

    assert (web / "package.json").exists()
    assert (web / "Dockerfile").exists()
    assert (web / "nginx.conf").read_text().count("listen 8080") == 1
    assert "proxy_pass http://api:8000" in (web / "nginx.conf").read_text()
    assert "proxy_pass http://ingest:8001" in (web / "nginx.conf").read_text()
    assert (agent / "example.py").exists()
    assert (agent / "Dockerfile").exists()


def test_minimal_sam_flow_matches_alias_and_reports_unknown():
    from services.backend.app import api
    from services.backend.app.api import CatalogSoftware, Installation, dashboard_summary

    api.catalog.clear()
    api.installations.clear()
    api.add_catalog_item(CatalogSoftware(name="Google Chrome", publisher="Google LLC"))
    api.add_catalog_item(CatalogSoftware(name="WinRAR", policy_status="prohibited"))

    api.add_installation(Installation(computer_id="pc-1", name="chrome.exe"))
    api.add_installation(Installation(computer_id="pc-2", name="unknown-tool.exe"))
    api.add_installation(Installation(computer_id="pc-3", name="WinRAR"))

    summary = dashboard_summary()
    assert summary["matched"] == 2
    assert summary["unknown"] == 1
    assert summary["critical_risks"] == 1
