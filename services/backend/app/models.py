from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class SoftwareProduct(Base):
    __tablename__ = "software_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    normalized_name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    publisher: Mapped[str] = mapped_column(String(200), default="")
    version: Mapped[str] = mapped_column(String(100), default="")
    license_type: Mapped[str] = mapped_column(String(50), default="free")
    policy_status: Mapped[str] = mapped_column(String(50), default="current")
    license_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    installations: Mapped[list[Installation]] = relationship(back_populates="software")


class Installation(Base):
    __tablename__ = "installations"

    id: Mapped[int] = mapped_column(primary_key=True)
    computer_id: Mapped[str] = mapped_column(String(200), index=True)
    raw_name: Mapped[str] = mapped_column(String(300))
    publisher: Mapped[str] = mapped_column(String(200), default="")
    version: Mapped[str] = mapped_column(String(100), default="")
    canonical_name: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)
    match_status: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    software_id: Mapped[int | None] = mapped_column(ForeignKey("software_products.id", ondelete="SET NULL"), nullable=True)

    software: Mapped[SoftwareProduct | None] = relationship(back_populates="installations")


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    installation_id: Mapped[int] = mapped_column(ForeignKey("installations.id"), index=True)
    risk: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
