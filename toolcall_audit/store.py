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
