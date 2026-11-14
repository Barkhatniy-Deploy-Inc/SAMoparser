from __future__ import annotations

import csv
import io
import re
from collections import Counter
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .db import get_db
from .models import Installation as InstallationRow
from .models import Device, SoftwareProduct

app = FastAPI(
    title="SAMoparser — API учёта программного обеспечения",
    description=(
        "API прототипа системы управления программными активами. "
        "Позволяет вести каталог ПО, загружать установки, сопоставлять названия "
        "и выявлять лицензионные и внутренние риски."
    ),
    version="1.0.0",
)


class CatalogSoftware(BaseModel):
    name: str = Field(min_length=1, max_length=200, description="Каноническое название программного продукта")
    publisher: str = Field(default="", description="Издатель или разработчик ПО")
    version: str = Field(default="", description="Версия продукта")
    license_type: str = Field(default="free", description="Тип лицензии: free, paid или условно-бесплатная")
    policy_status: str = Field(default="current", description="Статус политики: current, outdated или prohibited")
    license_count: int | None = Field(default=None, ge=0, description="Количество доступных лицензий")


class Installation(BaseModel):
    computer_id: str = Field(min_length=1, max_length=200, description="Идентификатор компьютера")
    name: str = Field(min_length=1, max_length=300, description="Исходное название установленного ПО")
    publisher: str = Field(default="", description="Издатель из источника инвентаризации")
    version: str = Field(default="", description="Версия из источника инвентаризации")


class DeviceInput(BaseModel):
    computer_id: str = Field(min_length=1, max_length=200, description="Уникальный идентификатор компьютера")
    display_name: str = Field(default="", max_length=200, description="Отображаемое имя компьютера")
    department: str = Field(default="", max_length=200, description="Подразделение")
    user_name: str = Field(default="", max_length=200, description="Пользователь компьютера")
    operating_system: str = Field(default="", max_length=100, description="Операционная система")


class ReviewDecision(BaseModel):
    software_name: str = Field(min_length=1, description="Исходное название, которое нужно подтвердить")
    catalog_name: str = Field(min_length=1, description="Название продукта из каталога")


def normalize_name(value: str) -> str:
    """Создать стабильный ключ для вариантов названий процессов и программ."""
    value = value.lower().replace("_", " ").replace("-", " ")
    value = re.sub(r"\.(exe|com)$", "", value)
    value = re.sub(r"\b(v\d+(?:\.\d+)*|version\s+\S+)\b", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    normalized = {"google chrome": "chrome", "chrome": "chrome"}.get(value, value)
    if not normalized:
        raise ValueError("Название ПО не может быть пустым после нормализации")
    return normalized


def catalog_view(row: SoftwareProduct) -> dict[str, Any]:
    return {"name": row.name, "publisher": row.publisher, "version": row.version, "license_type": row.license_type, "policy_status": row.policy_status, "license_count": row.license_count}


def installation_view(row: InstallationRow) -> dict[str, Any]:
    return {"computer_id": row.computer_id, "name": row.raw_name, "publisher": row.publisher, "version": row.version, "canonical_name": row.canonical_name, "match_status": row.match_status, "match_score": row.match_score}


def match_installation(item: Installation, products: list[SoftwareProduct]) -> dict[str, Any]:
    key = normalize_name(item.name)
    candidate = next((entry for entry in products if entry.normalized_name == key), None)
    return {**item.model_dump(), "canonical_name": candidate.name if candidate else None, "match_status": "matched" if candidate else "unknown", "match_score": 1.0 if candidate else 0.0, "software_id": candidate.id if candidate else None}


def risk_for(item: InstallationRow, used: int, products_by_id: dict[int, SoftwareProduct]) -> dict[str, Any] | None:
    if item.canonical_name is None:
        return {"computer_id": item.computer_id, "software": item.raw_name, "risk": "unknown", "severity": "medium", "reason": "ПО не найдено в каталоге"}
    entry = products_by_id.get(item.software_id) if item.software_id is not None else None
    if entry is None:
        return None
    if entry.policy_status == "prohibited":
        return {"computer_id": item.computer_id, "software": entry.name, "risk": "prohibited", "severity": "critical", "reason": "ПО запрещено внутренней политикой"}
    if entry.policy_status == "outdated":
        return {"computer_id": item.computer_id, "software": entry.name, "risk": "outdated", "severity": "medium", "reason": "Версия ПО устарела"}
    if entry.license_count is not None and used > entry.license_count:
        return {"computer_id": item.computer_id, "software": entry.name, "risk": "license_shortage", "severity": "high", "reason": f"Установок: {used}, лицензий: {entry.license_count}"}
    return None


@app.get("/health", summary="Проверка работоспособности сервиса", tags=["Служебные"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", summary="Проверка готовности сервиса и базы данных", tags=["Служебные"])
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/metrics", response_class=PlainTextResponse, summary="Метрики сервиса", tags=["Служебные"])
def metrics() -> str:
    return "# SAMoparser metrics placeholder\n"


@app.post("/api/v1/devices", status_code=201, summary="Зарегистрировать компьютер", tags=["Компьютеры"])
def add_device(item: DeviceInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    device = db.scalar(select(Device).where(Device.computer_id == item.computer_id))
    if device is None:
        device = Device(computer_id=item.computer_id)
        db.add(device)
    device.display_name = item.display_name
    device.department = item.department
    device.user_name = item.user_name
    device.operating_system = item.operating_system
    db.commit()
    return device_view(device)


def device_view(device: Device) -> dict[str, Any]:
    return {"computer_id": device.computer_id, "display_name": device.display_name, "department": device.department, "user_name": device.user_name, "operating_system": device.operating_system}


@app.get("/api/v1/devices", summary="Получить зарегистрированные компьютеры", tags=["Компьютеры"])
def get_devices(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [device_view(device) for device in db.scalars(select(Device).order_by(Device.id))]


@app.delete("/api/v1/devices/{computer_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить компьютер", tags=["Компьютеры"])
def delete_device(computer_id: str, db: Session = Depends(get_db)) -> Response:
    device = db.scalar(select(Device).where(Device.computer_id == computer_id))
    if device is None:
        raise HTTPException(status_code=404, detail="Компьютер не найден")
    db.delete(device)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/v1/catalog", status_code=201, summary="Добавить или обновить ПО в каталоге", tags=["Каталог ПО"])
def add_catalog_item(item: CatalogSoftware, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        normalized = normalize_name(item.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = db.scalar(select(SoftwareProduct).where(SoftwareProduct.normalized_name == normalized))
    if row is None:
        row = SoftwareProduct(normalized_name=normalized)
        db.add(row)
    row.name, row.publisher, row.version = item.name, item.publisher, item.version
    row.license_type, row.policy_status, row.license_count = item.license_type, item.policy_status, item.license_count
    db.commit()
    return catalog_view(row)


@app.get("/api/v1/catalog", summary="Получить каталог разрешённого ПО", tags=["Каталог ПО"])
def get_catalog(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [catalog_view(row) for row in db.scalars(select(SoftwareProduct).order_by(SoftwareProduct.id))]


@app.delete("/api/v1/catalog/{name}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить ПО из каталога", tags=["Каталог ПО"])
def delete_catalog_item(name: str, db: Session = Depends(get_db)) -> Response:
    try:
        normalized = normalize_name(name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    product = db.scalar(select(SoftwareProduct).where(SoftwareProduct.normalized_name == normalized))
    if product is None:
        raise HTTPException(status_code=404, detail="Продукт не найден в каталоге")
    for installation in db.scalars(select(InstallationRow).where(InstallationRow.software_id == product.id)):
        installation.software_id = None
        installation.canonical_name = None
        installation.match_status = "unknown"
        installation.match_score = 0.0
    db.delete(product)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def import_rows(payload: list[Installation], db: Session) -> tuple[dict[str, Any], list[InstallationRow]]:
    products = list(db.scalars(select(SoftwareProduct)))
    devices = {device.computer_id: device for device in db.scalars(select(Device))}
    missing_devices = sorted({item.computer_id for item in payload if item.computer_id not in devices})
    if missing_devices:
        raise HTTPException(status_code=422, detail={"message": "Компьютеры не зарегистрированы", "computer_ids": missing_devices})
    records = [match_installation(item, products) for item in payload]
    inserted: list[InstallationRow] = []
    for record in records:
        row = InstallationRow(computer_id=record["computer_id"], raw_name=record["name"], publisher=record["publisher"], version=record["version"], canonical_name=record["canonical_name"], match_status=record["match_status"], match_score=record["match_score"], software_id=record["software_id"], device_id=devices[record["computer_id"]].id)
        db.add(row)
        inserted.append(row)
    db.commit()
    return {"accepted": len(records), "unknown": sum(x["match_status"] == "unknown" for x in records)}, inserted


@app.post("/api/v1/installations", status_code=201, summary="Добавить одну установку", tags=["Установки"])
def add_installation(item: Installation, db: Session = Depends(get_db)) -> dict[str, Any]:
    _, inserted = import_rows([item], db)
    return installation_view(inserted[0])


@app.post("/api/v1/import/installations", status_code=201, summary="Импортировать установки из JSON", tags=["Импорт"])
def import_installations(payload: list[Installation], db: Session = Depends(get_db)) -> dict[str, Any]:
    result, _ = import_rows(payload, db)
    return result


@app.post("/api/v1/import/installations/csv", status_code=201, summary="Импортировать установки из CSV", tags=["Импорт"])
def import_installations_csv(csv_text: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = [Installation(computer_id=row.get("computer_id") or row.get("serial_number") or "", name=row.get("name") or row.get("displayname") or "", publisher=row.get("publisher") or "", version=row.get("version") or "") for row in reader]
    result, _ = import_rows(rows, db)
    return result


@app.get("/api/v1/installations", summary="Получить список установок", tags=["Установки"])
def get_installations(status: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    query = select(InstallationRow).order_by(InstallationRow.id)
    if status is not None:
        query = query.where(InstallationRow.match_status == status)
    return [installation_view(row) for row in db.scalars(query)]


@app.delete("/api/v1/installations/{installation_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить установку", tags=["Установки"])
def delete_installation(installation_id: int, db: Session = Depends(get_db)) -> Response:
    installation = db.get(InstallationRow, installation_id)
    if installation is None:
        raise HTTPException(status_code=404, detail="Установка не найдена")
    db.delete(installation)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def collect_risks(db: Session) -> list[dict[str, Any]]:
    rows = list(db.scalars(select(InstallationRow).order_by(InstallationRow.id)))
    products = {row.id: row for row in db.scalars(select(SoftwareProduct))}
    counts = Counter(row.canonical_name or row.raw_name for row in rows)
    return [risk for row in rows if (risk := risk_for(row, counts[row.canonical_name or row.raw_name], products)) is not None]


@app.get("/api/v1/risks", summary="Получить выявленные риски", tags=["Риски"])
def get_risks(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return collect_risks(db)


@app.get("/api/v1/dashboard/summary", summary="Получить сводку для панели управления", tags=["Панель управления"])
def dashboard_summary(db: Session = Depends(get_db)) -> dict[str, int]:
    risks = collect_risks(db)
    rows = list(db.scalars(select(InstallationRow)))
    return {"catalog_software": len(list(db.scalars(select(SoftwareProduct)))), "installations": len(rows), "matched": sum(x.match_status == "matched" for x in rows), "unknown": sum(x.match_status == "unknown" for x in rows), "critical_risks": sum(x["severity"] == "critical" for x in risks), "high_risks": sum(x["severity"] == "high" for x in risks), "medium_risks": sum(x["severity"] == "medium" for x in risks)}


@app.post("/api/v1/review", summary="Подтвердить сопоставление ПО", tags=["Проверка"])
def review_match(decision: ReviewDecision, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        normalized = normalize_name(decision.catalog_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    product = db.scalar(select(SoftwareProduct).where(SoftwareProduct.normalized_name == normalized))
    if product is None:
        raise HTTPException(status_code=422, detail="Продукт не найден в каталоге")
    rows = list(db.scalars(select(InstallationRow).where(InstallationRow.raw_name == decision.software_name)))
    if not rows:
        raise HTTPException(status_code=404, detail="installation not found")
    for row in rows:
        row.canonical_name, row.match_status, row.match_score, row.software_id = product.name, "matched", 1.0, product.id
    db.commit()
    return {"updated": len(rows)}
