"""Replay a recorded agent session against a policy and build the report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Session, SessionReport, ToolCall, Verdict
from .policy import Policy


def load_session(path: str | Path) -> Session:
    """Read a session JSON file and validate it into a Session model."""
    raw = Path(path).read_text(encoding="utf-8")
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"session file {path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"session file {path} must hold a JSON object")
    return Session.model_validate(payload)


def _argument_keys(call: ToolCall) -> set[str]:
    """Top-level argument names of a call, used to compare payload shapes."""
    return set(call.arguments.keys())


def detect_drift(session: Session, policy: Policy) -> list[str]:
    """Return the call ids whose tool or payload shape no policy rule covers.

    A call drifts when its tool is not mentioned by any rule, or when the tool is
    covered but none of the rules for that tool mention any of the argument names
    the call actually sent. The second case is the one that bites in practice: the
    tool is known, the arguments changed after a model upgrade.
    """
    covered = policy.covered_tools()
    known_keys: dict[str, set[str]] = {}
    for rule in policy.rules:
        known_keys.setdefault(rule.tool, set()).update(rule.when.keys())

    drifted: list[str] = []
    for call in session.calls:
        if call.tool not in covered:
            drifted.append(call.call_id)
            continue
        sent = _argument_keys(call)
        if not sent:
            continue
        expected = known_keys.get(call.tool, set())
        if expected and not (sent & expected):
            drifted.append(call.call_id)
    return drifted


def replay(session: Session, policy: Policy) -> SessionReport:
    """Evaluate every call in order and summarise the verdicts."""
    verdicts: list[Verdict] = [policy.evaluate(call) for call in session.calls]
    allowed = sum(1 for v in verdicts if v.decision == "allow")
    review = sum(1 for v in verdicts if v.decision == "review")
    denied = sum(1 for v in verdicts if v.decision == "deny")
    return SessionReport(
        session_id=session.session_id,
        agent=session.agent,
        total=len(verdicts),
        allowed=allowed,
        review=review,
        denied=denied,
        verdicts=verdicts,
        drift=detect_drift(session, policy),
    )
