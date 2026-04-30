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


def make_engine(url: str) -> Engine:
    """Build an engine for a SQLAlchemy URL; SQLite URLs get a shared connection."""
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, future=True)
    return create_engine(url, pool_pre_ping=True, future=True)


def init_db(engine: Engine) -> None:
    """Create the tables when they do not exist yet."""
    Base.metadata.create_all(engine)


def save_report(engine: Engine, report: SessionReport) -> None:
    """Persist a report, replacing any earlier rows for the same session."""
    verdicts = {verdict.call_id: verdict for verdict in report.verdicts}
    with OrmSession(engine) as db:
        db.execute(delete(SessionRow).where(SessionRow.session_id == report.session_id))
        db.flush()

        row = SessionRow(
            session_id=report.session_id,
            agent=report.agent,
            started_at=report.started_at,
            total=report.total,
            allowed=report.allowed,
            review=report.review,
            denied=report.denied,
            drift=json.dumps(report.drift),
        )
        db.add(row)

        for position, call in enumerate(report.calls):
            call_row = CallRow(
                session_id=report.session_id,
                position=position,
                call_id=call.call_id,
                tool=call.tool,
                arguments=json.dumps(call.arguments, sort_keys=True),
                started_at=call.started_at,
                duration_ms=call.duration_ms,
            )
            db.add(call_row)
            db.flush()
            verdict = verdicts.get(call.call_id)
            if verdict is not None:
                db.add(
                    VerdictRow(
                        call_pk=call_row.id,
                        call_id=verdict.call_id,
                        tool=verdict.tool,
                        decision=verdict.decision,
                        rule=verdict.rule,
                        reason=verdict.reason,
                    )
                )
        db.commit()


def load_report(engine: Engine, session_id: str) -> SessionReport | None:
    """Rebuild a stored report, or return None when the session is unknown."""
    with OrmSession(engine) as db:
        row = db.get(SessionRow, session_id)
        if row is None:
            return None
        calls = list(db.scalars(select(CallRow).where(CallRow.session_id == session_id).order_by(CallRow.position)))
        verdicts = [
            Verdict(
                call_id=call.verdict.call_id,
                tool=call.verdict.tool,
                decision=call.verdict.decision,
                rule=call.verdict.rule,
                reason=call.verdict.reason,
            )
            for call in calls
            if call.verdict is not None
        ]
        return SessionReport(
            session_id=row.session_id,
            agent=row.agent,
            started_at=row.started_at,
            total=row.total,
            allowed=row.allowed,
            review=row.review,
            denied=row.denied,
            verdicts=verdicts,
            drift=json.loads(row.drift or "[]"),
            calls=[_call_from_row(call) for call in calls],
        )


def _call_from_row(row: CallRow) -> Any:
    """Turn a stored call row back into the Pydantic model the report uses."""
    from toolcall_audit.models import ToolCall

    return ToolCall(
        call_id=row.call_id,
        tool=row.tool,
        arguments=json.loads(row.arguments or "{}"),
        started_at=row.started_at,
        duration_ms=row.duration_ms,
    )
