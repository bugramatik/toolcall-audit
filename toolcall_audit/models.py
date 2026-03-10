"""Pydantic models for recorded agent sessions, tool calls and verdicts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Decision = Literal["allow", "review", "deny"]


class ToolCall(BaseModel):
    """One tool invocation recorded from an agent run."""

    call_id: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    duration_ms: int = Field(ge=0)


class Session(BaseModel):
    """A recorded run of an agent, in call order."""

    session_id: str
    agent: str
    started_at: datetime
    calls: list[ToolCall] = Field(default_factory=list)


class Verdict(BaseModel):
    """The decision a policy made for a single call."""

    call_id: str
    tool: str
    decision: Decision
    rule: str
    reason: str


class SessionReport(BaseModel):
    """The outcome of replaying a session against a policy."""

    session_id: str
    agent: str
    total: int
    allowed: int
    review: int
    denied: int
    verdicts: list[Verdict] = Field(default_factory=list)
    drift: list[str] = Field(default_factory=list)

    @property
    def clean(self) -> bool:
        """True when nothing was denied and no drift was found."""
        return self.denied == 0 and not self.drift

    def counts(self) -> dict[str, int]:
        """Decision counts keyed by decision name, for tables and summaries."""
        return {"allow": self.allowed, "review": self.review, "deny": self.denied}


class ReplayRequest(BaseModel):
    """Body of the replay route: a session and an optional policy path."""

    session: Session
    policy_path: str | None = None
