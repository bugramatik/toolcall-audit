"""Tests for session replay, counting and drift detection."""

from __future__ import annotations

import json
from pathlib import Path

from toolcall_audit.models import Session
from toolcall_audit.policy import load_policy
from toolcall_audit.replay import detect_drift, load_session, replay

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "policy" / "default.yaml"
SESSION_PATH = ROOT / "data" / "session-example.json"


def test_load_session() -> None:
    session = load_session(str(SESSION_PATH))
    assert isinstance(session, Session)
    assert session.session_id == "sess-2025-03-04-a"
    assert session.agent == "support-assistant"
    assert len(session.calls) == 12
    assert session.calls[0].tool == "file.read"


def test_replay_counts() -> None:
    session = load_session(str(SESSION_PATH))
    policy = load_policy(str(POLICY_PATH))
    report = replay(session, policy)
    assert report.total == 12
    assert report.allowed + report.review + report.denied == report.total
    assert report.denied >= 1
    assert report.allowed >= 1


def test_verdicts_follow_call_order() -> None:
    session = load_session(str(SESSION_PATH))
    policy = load_policy(str(POLICY_PATH))
    report = replay(session, policy)
    assert [v.call_id for v in report.verdicts] == [c.call_id for c in session.calls]


def test_drift_flags_unknown_tool() -> None:
    session = load_session(str(SESSION_PATH))
    policy = load_policy(str(POLICY_PATH))
    drift = detect_drift(session, policy)
    assert "calendar.create" in drift
    assert "file.read" not in drift


def test_replay_is_deterministic() -> None:
    session = load_session(str(SESSION_PATH))
    policy = load_policy(str(POLICY_PATH))
    first = replay(session, policy)
    second = replay(session, policy)
    assert first.model_dump() == second.model_dump()
    json.dumps(first.model_dump())
