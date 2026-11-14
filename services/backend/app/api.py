from __future__ import annotations

import csv
import io
import re
from collections import Counter
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field


app = FastAPI(title="SAMoparser API")


class CatalogSoftware(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    publisher: str = ""
    version: str = ""
    license_type: str = "free"
    policy_status: str = "current"
    license_count: int | None = Field(default=None, ge=0)


class Installation(BaseModel):
    computer_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=300)
    publisher: str = ""
    version: str = ""


class ReviewDecision(BaseModel):
    software_name: str = Field(min_length=1)
    catalog_name: str = Field(min_length=1)


catalog: list[dict[str, Any]] = []
installations: list[dict[str, Any]] = []


def normalize_name(value: str) -> str:
    """Create a stable key for common OS/process naming variants."""
    value = value.lower().replace("_", " ").replace("-", " ")
    value = re.sub(r"\.(exe|com)$", "", value)
    value = re.sub(r"\b(v\d+(?:\.\d+)*|version\s+\S+)\b", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    aliases = {"google chrome": "chrome", "chrome": "chrome"}
    return aliases.get(value, value)


def match_installation(item: Installation) -> dict[str, Any]:
    key = normalize_name(item.name)
    candidates = [entry for entry in catalog if normalize_name(entry["name"]) == key]
    if not candidates:
        return {**item.model_dump(), "canonical_name": None, "match_status": "unknown", "match_score": 0.0}
    entry = candidates[0]
    return {
        **item.model_dump(),
        "canonical_name": entry["name"],
        "match_status": "matched",
        "match_score": 1.0,
    }


def risk_for(item: dict[str, Any], used: int) -> dict[str, Any] | None:
    if item["canonical_name"] is None:
        return {"computer_id": item["computer_id"], "software": item["name"], "risk": "unknown", "severity": "medium", "reason": "ПО не найдено в каталоге"}
    entry = next((x for x in catalog if x["name"] == item["canonical_name"]), None)
    if entry is None:
        return None
    if entry["policy_status"] == "prohibited":
        return {"computer_id": item["computer_id"], "software": entry["name"], "risk": "prohibited", "severity": "critical", "reason": "ПО запрещено внутренней политикой"}
    if entry["policy_status"] == "outdated":
        return {"computer_id": item["computer_id"], "software": entry["name"], "risk": "outdated", "severity": "medium", "reason": "Версия ПО устарела"}
    if entry["license_count"] is not None and used > entry["license_count"]:
        return {"computer_id": item["computer_id"], "software": entry["name"], "risk": "license_shortage", "severity": "high", "reason": f"Установок: {used}, лицензий: {entry['license_count']}"}
    return None


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    return "# SAMoparser metrics placeholder\n"


@app.post("/api/v1/catalog", status_code=201)
def add_catalog_item(item: CatalogSoftware) -> dict[str, Any]:
    record = item.model_dump()
    catalog[:] = [x for x in catalog if normalize_name(x["name"]) != normalize_name(item.name)]
    catalog.append(record)
    return record


@app.get("/api/v1/catalog")
def get_catalog() -> list[dict[str, Any]]:
    return catalog


@app.post("/api/v1/installations", status_code=201)
def add_installation(item: Installation) -> dict[str, Any]:
    record = match_installation(item)
    installations.append(record)
    return record


@app.post("/api/v1/import/installations", status_code=201)
def import_installations(payload: list[Installation]) -> dict[str, Any]:
    records = [match_installation(item) for item in payload]
    installations.extend(records)
    return {"accepted": len(records), "unknown": sum(x["match_status"] == "unknown" for x in records)}


@app.post("/api/v1/import/installations/csv", status_code=201)
def import_installations_csv(csv_text: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = [Installation(computer_id=row.get("computer_id") or row.get("serial_number") or "", name=row.get("name") or row.get("displayname") or "", publisher=row.get("publisher") or "", version=row.get("version") or "") for row in reader]
    return import_installations(rows)


@app.get("/api/v1/installations")
def get_installations(status: str | None = None) -> list[dict[str, Any]]:
    return [x for x in installations if status is None or x["match_status"] == status]


@app.get("/api/v1/risks")
def get_risks() -> list[dict[str, Any]]:
    counts = Counter(x["canonical_name"] or x["name"] for x in installations)
    return [risk for item in installations if (risk := risk_for(item, counts[item["canonical_name"] or item["name"]])) is not None]


@app.get("/api/v1/dashboard/summary")
def dashboard_summary() -> dict[str, int]:
    risks = get_risks()
    return {
        "catalog_software": len(catalog),
        "installations": len(installations),
        "matched": sum(x["match_status"] == "matched" for x in installations),
        "unknown": sum(x["match_status"] == "unknown" for x in installations),
        "critical_risks": sum(x["severity"] == "critical" for x in risks),
        "high_risks": sum(x["severity"] == "high" for x in risks),
        "medium_risks": sum(x["severity"] == "medium" for x in risks),
    }


@app.post("/api/v1/review", status_code=200)
def review_match(decision: ReviewDecision) -> dict[str, Any]:
    changed = 0
    for item in installations:
        if item["name"] == decision.software_name:
            item["canonical_name"] = decision.catalog_name
            item["match_status"] = "matched"
            item["match_score"] = 1.0
            changed += 1
    if not changed:
        raise HTTPException(status_code=404, detail="installation not found")
    return {"updated": changed}
