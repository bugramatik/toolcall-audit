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
