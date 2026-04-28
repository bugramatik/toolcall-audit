"""Load a declarative YAML policy and decide each tool call against its rules.

A policy is a list of rules. Each rule names a tool (or ``*`` for any tool),
optionally narrows the match with a ``when`` block of argument conditions, and
carries a decision: ``allow``, ``review`` or ``deny``. When several rules match
the same call the most restrictive decision wins, so a broad allow rule can be
written first and a narrow deny rule later without reordering anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from toolcall_audit.models import ToolCall, Verdict

DECISIONS = ("allow", "review", "deny")
# Higher number means the decision wins when rules overlap.
SEVERITY = {"allow": 0, "review": 1, "deny": 2}


class Rule(BaseModel):
    """One policy rule: which tool, under which conditions, and the decision."""

    name: str
    tool: str = "*"
    decision: str
    when: dict[str, Any] = Field(default_factory=dict)

    @field_validator("decision")
    @classmethod
    def _known_decision(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in DECISIONS:
            raise ValueError(f"unknown decision {value!r}, expected one of {DECISIONS}")
        return value

    def matches(self, call: ToolCall) -> bool:
        """True when the rule's tool pattern and every ``when`` condition hold."""
        if self.tool != "*" and self.tool != call.tool:
            return False
        return all(_condition_holds(call.arguments, key, expected) for key, expected in self.when.items())


class Policy(BaseModel):
    """A versioned set of rules plus the decision used when nothing matches."""

    version: str = "1"
    default: str = "review"
    rules: list[Rule] = Field(default_factory=list)

    @field_validator("default")
    @classmethod
    def _known_default(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in DECISIONS:
            raise ValueError(f"unknown default decision {value!r}")
        return value

    def evaluate(self, call: ToolCall) -> Verdict:
        """Decide one call, returning the winning rule and a short reason."""
        matched = [rule for rule in self.rules if rule.matches(call)]
        if not matched:
            return Verdict(
                call_id=call.call_id,
                tool=call.tool,
                decision=self.default,
                rule="default",
                reason=f"no rule covers {call.tool}, policy default applies",
            )

        winner = max(matched, key=lambda rule: SEVERITY[rule.decision])
        if len(matched) == 1:
            reason = f"matched rule {winner.name}"
        else:
            others = ", ".join(rule.name for rule in matched if rule is not winner)
            reason = f"matched rule {winner.name}, stricter than {others}"
        return Verdict(
            call_id=call.call_id,
            tool=call.tool,
            decision=winner.decision,
            rule=winner.name,
            reason=reason,
        )

    def covered_tools(self) -> set[str]:
        """Tools named by at least one rule; ``*`` rules are not counted."""
        return {rule.tool for rule in self.rules if rule.tool != "*"}

    def covers_tool(self, tool: str) -> bool:
        """True when any rule, including a wildcard rule, can decide this tool."""
        return any(rule.tool in ("*", tool) for rule in self.rules)


def _condition_holds(arguments: dict[str, Any], key: str, expected: Any) -> bool:
    """Check one ``when`` entry against the call arguments.

    Supported forms:
      ``key: value``            equality
      ``key: {in: [a, b]}``     membership
      ``key: {prefix: /tmp}``   string prefix
      ``key: {contains: ..}``   substring
      ``key: {exists: true}``   presence of the key
    """
    present = key in arguments
    actual = arguments.get(key)

    if isinstance(expected, dict):
        if "exists" in expected:
            return present is bool(expected["exists"])
        if not present:
            return False
        if "in" in expected:
            return actual in expected["in"]
        if "prefix" in expected:
            return isinstance(actual, str) and actual.startswith(str(expected["prefix"]))
        if "contains" in expected:
            needle = str(expected["contains"])
            if isinstance(actual, str):
                return needle in actual
            if isinstance(actual, (list, tuple, set)):
                return needle in actual
            return False
        raise ValueError(f"unsupported condition {expected!r} for argument {key!r}")

    return present and actual == expected


def load_policy(path: str | Path) -> Policy:
    """Read a YAML policy file and validate it."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"policy file {path} must contain a mapping at the top level")
    return Policy.model_validate(raw)
