"""Command line entry point: replay a session file and print a summary table."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from toolcall_audit import __version__
from toolcall_audit.models import SessionReport
from toolcall_audit.policy import load_policy
from toolcall_audit.replay import load_session, replay
