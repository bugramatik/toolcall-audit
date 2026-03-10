"""Rough token estimates for tool call payloads.

A real tokenizer is not worth the dependency here: the report only needs a
stable, comparable weight per call so a reviewer can spot the calls that
carry a large payload. The estimate is characters divided by four, rounded
up, which is close enough for JSON arguments.
"""

from __future__ import annotations

import json
from typing import Any

from toolcall_audit.models import ToolCall

CHARS_PER_TOKEN = 4


def estimate_tokens(value: Any) -> int:
    """Estimate the token count of a JSON-serialisable value."""
    if value is None:
        return 0
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, sort_keys=True, default=str)
        except (TypeError, ValueError):
            text = str(value)
    if not text:
        return 0
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def estimate_call_tokens(call: ToolCall) -> int:
    """Estimate the payload weight of one tool call, tool name included."""
    return estimate_tokens(call.tool) + estimate_tokens(call.arguments)
