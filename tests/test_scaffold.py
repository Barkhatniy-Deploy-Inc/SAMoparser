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
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from services.backend.app import api
    from services.backend.app.db import Base
    from services.backend.app.api import CatalogSoftware, DeviceInput, Installation

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        api.add_catalog_item(CatalogSoftware(name="Google Chrome", publisher="Google LLC"), db)
        api.add_catalog_item(CatalogSoftware(name="WinRAR", policy_status="prohibited"), db)
        api.add_device(DeviceInput(computer_id="pc-1"), db)
        api.add_device(DeviceInput(computer_id="pc-2"), db)
        api.add_device(DeviceInput(computer_id="pc-3"), db)
        api.add_installation(Installation(computer_id="pc-1", name="chrome.exe"), db)
        api.add_installation(Installation(computer_id="pc-2", name="unknown-tool.exe"), db)
        api.add_installation(Installation(computer_id="pc-3", name="WinRAR"), db)
        summary = api.dashboard_summary(db)

    assert summary["matched"] == 2
    assert summary["unknown"] == 1
    assert summary["critical_risks"] == 1


def test_delete_endpoints_remove_records_and_unmatch_catalog_software():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from services.backend.app import api
    from services.backend.app.api import CatalogSoftware, DeviceInput, Installation
    from services.backend.app.db import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        api.add_device(DeviceInput(computer_id="pc-delete"), db)
        api.add_catalog_item(CatalogSoftware(name="Test Tool"), db)
        created = api.add_installation(Installation(computer_id="pc-delete", name="Test Tool"), db)
        installation_id = db.query(api.InstallationRow).first().id

        api.delete_catalog_item("Test Tool", db)
        assert api.get_installations(db=db)[0]["match_status"] == "unknown"
        api.delete_installation(installation_id, db)
        api.delete_device("pc-delete", db)
        assert api.get_installations(db=db) == []
