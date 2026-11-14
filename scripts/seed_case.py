"""Загрузить тестовые данные кейса из Excel-файлов в PostgreSQL."""

from __future__ import annotations

import re
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from sqlalchemy import select

from app.api import normalize_name
from app.db import SessionLocal
from app.models import Device, Installation, SoftwareProduct

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def read_workbook(path: Path) -> list[list[str]]:
    """Прочитать первый лист XLSX без дополнительных библиотек."""
    with ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(text.text or "" for text in item.findall(".//m:t", NS))
                for item in root.findall("m:si", NS)
            ]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
        sheet = workbook.find(".//m:sheets/m:sheet", NS)
        if sheet is None:
            return []
        relationship_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = targets[relationship_id]
        target = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
        root = ET.fromstring(archive.read(target))
        rows: list[list[str]] = []
        for row in root.findall(".//m:sheetData/m:row", NS):
            values: list[str] = []
            for cell in row.findall("m:c", NS):
                value = cell.find("m:v", NS)
                text = "" if value is None else value.text or ""
                if cell.attrib.get("t") == "s" and text:
                    text = shared[int(text)]
                values.append(text.strip())
            rows.append(values)
        return rows


def find_file(files: list[Path], marker: str) -> Path:
    for path in files:
        if marker in " ".join(read_workbook(path)[0]).lower():
            return path
    raise FileNotFoundError(f"Не найден Excel-файл с заголовком: {marker}")


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def main() -> None:
    files = list(Path("/app/docs").glob("*.xlsx"))
    installed_file = next(path for path in files if any("COMPUTERS.SERIAL_NUMBER" in " ".join(row) for row in read_workbook(path)[:5]))
    catalog_file = next(path for path in files if any("БПО" in " ".join(row) for row in read_workbook(path)[:20]))
    installed_rows = read_workbook(installed_file)
    catalog_rows = read_workbook(catalog_file)
    installed_rows = installed_rows[next(index for index, row in enumerate(installed_rows) if "COMPUTERS.SERIAL_NUMBER" in " ".join(row)) + 1 :]
    catalog_rows = catalog_rows[next(index for index, row in enumerate(catalog_rows) if "БПО" in " ".join(row)) + 1 :]

    with SessionLocal() as db:
        devices: dict[str, Device] = {}
        for row in installed_rows:
            if not row or not clean(row[0]):
                continue
            computer_id = clean(row[0])
            device = db.scalar(select(Device).where(Device.computer_id == computer_id))
            if device is None:
                device = Device(computer_id=computer_id, display_name=computer_id, operating_system="Windows")
                db.add(device)
                db.flush()
            devices[computer_id] = device

        products: dict[str, SoftwareProduct] = {}
        for row in catalog_rows:
            if not row or not clean(row[0]) or clean(row[0]) in {"2", "3"}:
                continue
            name = clean(row[0])
            try:
                normalized = normalize_name(name)
            except ValueError:
                continue
            if normalized in products:
                continue
            product = db.scalar(select(SoftwareProduct).where(SoftwareProduct.normalized_name == normalized))
            if product is None:
                product = SoftwareProduct(name=name, normalized_name=normalized, version=clean(row[1]) if len(row) > 1 else "", publisher="", license_type="free", policy_status="current")
                db.add(product)
            products[normalized] = product
        db.flush()

        existing = db.scalar(select(Installation.id).limit(1))
        if existing is None:
            for row in installed_rows:
                if len(row) < 2 or not clean(row[0]) or not clean(row[1]):
                    continue
                computer_id, raw_name = clean(row[0]), clean(row[1])
                product = products.get(normalize_name(raw_name))
                db.add(Installation(computer_id=computer_id, raw_name=raw_name, publisher=clean(row[2]) if len(row) > 2 else "", version=clean(row[3]) if len(row) > 3 else "", canonical_name=product.name if product else None, match_status="matched" if product else "unknown", match_score=1.0 if product else 0.0, software_id=product.id if product else None, device_id=devices[computer_id].id))
        db.commit()
        print(f"Загружено компьютеров: {len(devices)}")
        print(f"Загружено продуктов в каталоге: {len(products)}")
        print(f"Установки: {'уже были в базе' if existing is not None else 'загружены'}")


if __name__ == "__main__":
    main()
