"""SQLAlchemy models and persistence for sessions, calls and verdicts.

The store keeps the raw call payloads next to the verdicts so a report can be
rebuilt later without the original session file. ``save_report`` is idempotent
per session: replaying the same session again replaces its rows.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, create_engine, delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session as OrmSession, mapped_column, relationship

from toolcall_audit.models import SessionReport, Verdict


class Base(DeclarativeBase):
    """Declarative base for every table in the audit store."""


class SessionRow(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allowed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    denied: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drift: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    calls: Mapped[list["CallRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="CallRow.position"
    )


class CallRow(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    call_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tool: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    session: Mapped[SessionRow] = relationship(back_populates="calls")
    verdict: Mapped["VerdictRow | None"] = relationship(
        back_populates="call", cascade="all, delete-orphan", uselist=False
    )


class VerdictRow(Base):
    __tablename__ = "verdicts"

    call_pk: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), primary_key=True)
    call_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tool: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    rule: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    call: Mapped[CallRow] = relationship(back_populates="verdict")

