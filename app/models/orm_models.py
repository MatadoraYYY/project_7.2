"""SQLAlchemy ORM models. No PII is stored - only anonymized identifiers."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    total_orders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_order_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    first_purchase_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_purchase_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    price_sensitivity: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    lifetime_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    preferred_channel: Mapped[str] = mapped_column(String(32), default="push", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    purchases: Mapped[list["Purchase"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    offers: Mapped[list["OfferRecord"]] = relationship(back_populates="customer", cascade="all, delete-orphan")


class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)

    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    had_discount: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="general", nullable=False)

    customer: Mapped["Customer"] = relationship(back_populates="purchases")


class OfferRecord(Base):
    __tablename__ = "offer_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    offer_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)

    offer_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    segment_at_generation: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)

    is_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    order_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_control_group: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    converted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    customer: Mapped["Customer"] = relationship(back_populates="offers")
