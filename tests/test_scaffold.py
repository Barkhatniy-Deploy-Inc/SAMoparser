import io
from pathlib import Path
from zipfile import ZipFile

import pytest


ROOT = Path(__file__).parents[1]


def test_backend_entrypoints_expose_health_readiness_and_metrics():
    from services.backend.app.api import app as api_app
    from services.backend.app.ingest import app as ingest_app

    for application in (api_app, ingest_app):
        paths = {route.path for route in application.routes}
        assert {"/health", "/ready", "/metrics"} <= paths


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
    from sqlalchemy.pool import StaticPool
    from sqlalchemy.orm import Session

    from services.backend.app import api
    from services.backend.app.db import Base
    from services.backend.app.api import CatalogSoftware, DeviceInput, Installation

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
        assert api.get_installations(status=None, limit=100, offset=0, db=db)["items"][0]["match_status"] == "unknown"
        api.delete_installation(installation_id, db)
        api.delete_device("pc-delete", db)
        assert api.get_installations(status=None, limit=100, offset=0, db=db)["items"] == []


def test_installations_are_paginated_and_filterable():
    from fastapi import HTTPException
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from services.backend.app import api
    from services.backend.app.api import DeviceInput, Installation
    from services.backend.app.db import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        api.add_device(DeviceInput(computer_id="pc-page"), db)
        for index in range(5):
            api.add_installation(Installation(computer_id="pc-page", name=f"tool-{index}"), db)

        page = api.get_installations(status=None, limit=2, offset=1, db=db)
        assert page["total"] == 5
        assert page["limit"] == 2
        assert page["offset"] == 1
        assert [item["name"] for item in page["items"]] == ["tool-1", "tool-2"]

        unknown_page = api.get_installations(status="unknown", limit=10, offset=0, db=db)
        assert unknown_page["total"] == 5
        assert len(unknown_page["items"]) == 5

        with pytest.raises(HTTPException) as error:
            api.get_installations(status=None, limit=501, offset=0, db=db)
        assert error.value.status_code == 422


def test_installation_import_is_idempotent_and_rejects_key_reuse_with_other_payload():
    from fastapi import HTTPException
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from services.backend.app import api
    from services.backend.app.api import DeviceInput, Installation
    from services.backend.app.db import Base
    from services.backend.app.models import ImportBatch, Installation as InstallationRow

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        api.add_device(DeviceInput(computer_id="pc-idempotency"), db)
        payload = [Installation(computer_id="pc-idempotency", name="unknown-app")]

        first = api.import_rows(payload, db, idempotency_key="batch-001")
        repeated = api.import_rows(payload, db, idempotency_key="batch-001")

        assert {key: value for key, value in repeated[0].items() if key != "replayed"} == {
            key: value for key, value in first[0].items() if key != "replayed"
        }
        assert repeated[0]["replayed"] is True
        assert len(list(db.scalars(select(InstallationRow)))) == 1
        assert len(list(db.scalars(select(ImportBatch)))) == 1

        changed_payload = [Installation(computer_id="pc-idempotency", name="different-app")]
        with pytest.raises(HTTPException) as error:
            api.import_rows(changed_payload, db, idempotency_key="batch-001")
        assert error.value.status_code == 409


def test_install_import_endpoints_require_file_and_accept_csv_upload():
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from services.backend.app import api
    from services.backend.app.db import Base, get_db
    from services.backend.app.models import Device

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as db:
            yield db

    api.app.dependency_overrides[get_db] = override_get_db
    try:
        with Session(engine) as db:
            db.add(Device(computer_id="PC-UPLOAD"))
            db.commit()
        client = TestClient(api.app)

        missing_file = client.post("/api/v1/import/installations")
        assert missing_file.status_code == 422

        csv_content = (
            "COMPUTERS.SERIAL_NUMBER,SOFTWARE.DISPLAYNAME,SOFTWARE.PUBLISHER,SOFTWARE.VERSION\n"
            "PC-UPLOAD,Example App,Example Publisher,1.0\n"
        )
        first = client.post(
            "/api/v1/import/installations",
            headers={"Idempotency-Key": "upload-001"},
            files={"file": ("installations.csv", csv_content, "text/csv")},
        )
        assert first.status_code == 201
        assert first.json()["accepted"] == 1
        assert first.json()["replayed"] is False

        repeated = client.post(
            "/api/v1/import/installations",
            headers={"Idempotency-Key": "upload-001"},
            files={"file": ("installations.csv", csv_content, "text/csv")},
        )
        assert repeated.status_code == 201
        assert repeated.json()["replayed"] is True

        malformed_xlsx = client.post(
            "/api/v1/import/installations",
            files={"file": ("installations.xlsx", b"not supported", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert malformed_xlsx.status_code == 422

        xlsx_buffer = io.BytesIO()
        with ZipFile(xlsx_buffer, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Установки" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row><c t="inlineStr"><is><t>COMPUTERS.SERIAL_NUMBER</t></is></c><c t="inlineStr"><is><t>SOFTWARE.DISPLAYNAME</t></is></c><c t="inlineStr"><is><t>SOFTWARE.PUBLISHER</t></is></c><c t="inlineStr"><is><t>SOFTWARE.VERSION</t></is></c></row>'
                '<row><c t="inlineStr"><is><t>PC-UPLOAD</t></is></c><c t="inlineStr"><is><t>XLSX Example</t></is></c><c t="inlineStr"><is><t>Example Publisher</t></is></c><c t="inlineStr"><is><t>3.0</t></is></c></row>'
                '</sheetData></worksheet>',
            )
        xlsx_upload = client.post(
            "/api/v1/import/installations",
            files={"file": ("installations.xlsx", xlsx_buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert xlsx_upload.status_code == 201
        assert xlsx_upload.json()["accepted"] == 1

        json_content = '[{"computer_id":"PC-UPLOAD","name":"JSON Example","version":"2.0"}]'
        json_upload = client.post(
            "/api/v1/import/installations",
            files={"file": ("installations.json", json_content, "application/json")},
        )
        assert json_upload.status_code == 201
        assert json_upload.json()["accepted"] == 1

        malformed_json = client.post(
            "/api/v1/import/installations",
            files={"file": ("broken.json", b"{invalid", "application/json")},
        )
        assert malformed_json.status_code == 422
    finally:
        api.app.dependency_overrides.clear()
