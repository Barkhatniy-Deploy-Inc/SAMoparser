"""Показать воспроизводимый baseline локальной базы SAMoparser."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Device, ImportBatch, Installation, SoftwareProduct


def main() -> None:
    with SessionLocal() as db:
        installation_count = db.scalar(select(func.count()).select_from(Installation)) or 0
        device_count = db.scalar(select(func.count()).select_from(Device)) or 0
        product_count = db.scalar(select(func.count()).select_from(SoftwareProduct)) or 0
        unique_names = db.scalar(select(func.count(func.distinct(Installation.raw_name)))) or 0
        unique_publishers = db.scalar(select(func.count(func.distinct(Installation.publisher)))) or 0
        statuses = Counter(db.scalars(select(Installation.match_status)))
        matched = db.scalar(
            select(func.count()).select_from(Installation).where(Installation.match_status == "matched")
        ) or 0
        import_count = db.scalar(select(func.count()).select_from(ImportBatch)) or 0

    print("SAMoparser baseline")
    print(f"installations={installation_count}")
    print(f"devices={device_count}")
    print(f"software_products={product_count}")
    print(f"unique_raw_names={unique_names}")
    print(f"unique_publishers={unique_publishers}")
    print(f"matched={matched}")
    print(f"unknown={statuses.get('unknown', 0)}")
    print(f"needs_review={statuses.get('needs_review', 0)}")
    print(f"confirmed={statuses.get('confirmed', 0)}")
    print(f"rejected={statuses.get('rejected', 0)}")
    print(f"import_batches={import_count}")


if __name__ == "__main__":
    main()
