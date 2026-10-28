"""Tests for policy loading and rule evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from toolcall_audit.models import ToolCall
from toolcall_audit.policy import Policy, Rule, load_policy

POLICY_PATH = Path(__file__).resolve().parents[1] / "policy" / "default.yaml"


def make_call(tool: str, arguments: dict | None = None) -> ToolCall:
    return ToolCall(
        call_id="call-1",
        tool=tool,
        arguments=arguments or {},
        started_at=datetime(2025, 3, 4, 9, 12, 0, tzinfo=timezone.utc),
        duration_ms=42,
    )


def test_load_policy_reads_rules() -> None:
    policy = load_policy(str(POLICY_PATH))
    assert policy.version == 1
    assert policy.default == "review"
    assert len(policy.rules) >= 8
    assert all(isinstance(rule, Rule) for rule in policy.rules)


def test_allow_rule_matches() -> None:
    policy = load_policy(str(POLICY_PATH))
    verdict = policy.evaluate(make_call("file.read", {"path": "/workspace/notes.md"}))
    assert verdict.decision == "allow"
    assert verdict.rule == "read-file-inside-workspace"
    assert verdict.call_id == "call-1"


def test_deny_wins_over_allow() -> None:
    policy = Policy(
        version=1,
        default="review",
        rules=[
            Rule(name="allow-all-reads", tool="file.read", decision="allow", when={}),
            Rule(
                name="deny-secrets",
                tool="file.read",
                decision="deny",
                when={"path_prefix": "/etc/"},
            ),
        ],
    )
    verdict = policy.evaluate(make_call("file.read", {"path": "/etc/passwd"}))
    assert verdict.decision == "deny"
    assert verdict.rule == "deny-secrets"


def test_default_applies() -> None:
    policy = load_policy(str(POLICY_PATH))
    verdict = policy.evaluate(make_call("calendar.create", {"title": "standup"}))
    assert verdict.decision == "review"
    assert verdict.rule == "default"
    assert "calendar.create" in verdict.reason


def test_covered_tools() -> None:
    policy = load_policy(str(POLICY_PATH))
    assert policy.covered_tools() == {
        "file.read",
        "file.write",
        "shell.exec",
        "http.request",
        "db.query",
    }


def test_missing_policy_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_policy(str(POLICY_PATH.parent / "does-not-exist.yaml"))
