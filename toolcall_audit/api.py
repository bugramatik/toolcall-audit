"""FastAPI app with health, replay and report routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from toolcall_audit import __version__, get_logger
from toolcall_audit.models import Session, SessionReport
from toolcall_audit.policy import Policy, load_policy
from toolcall_audit.replay import load_session, replay
from toolcall_audit.store import init_db, load_report, make_engine, save_report

log = get_logger(__name__)

DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "policy" / "default.yaml"
DEFAULT_DATABASE_URL = "sqlite:///./toolcall_audit.db"

app = FastAPI(title="Toolcall Audit", version=__version__)

_engine: Engine | None = None


def get_engine() -> Engine:
    """Return the process-wide engine, creating the tables on first use."""
    global _engine
    if _engine is None:
        _engine = make_engine(DEFAULT_DATABASE_URL)
        init_db(_engine)
    return _engine


class ReplayRequest(BaseModel):
    """Body of the replay route: a session file or an inline session."""

    session_path: str | None = None
    session: Session | None = None
    policy_path: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe used by the container and the dashboard."""
    return HealthResponse(status="ok", version=__version__)


@app.post("/replay", response_model=SessionReport)
def replay_session(
    request: ReplayRequest,
    engine: Engine = Depends(get_engine),
) -> SessionReport:
    """Replay a session against a policy, store the report and return it."""
    if request.session is not None:
        session = request.session
    elif request.session_path:
        try:
            session = load_session(request.session_path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=f"session file not found: {exc}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        raise HTTPException(status_code=422, detail="provide session_path or session")

    policy_path = request.policy_path or str(DEFAULT_POLICY)
    try:
        policy: Policy = load_policy(policy_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"policy file not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid policy: {exc}") from exc

    report = replay(session, policy)
    save_report(engine, report)
    log.info(
        "replayed %s: %d calls, %d denied, %d drift",
        report.session_id,
        report.total,
        report.denied,
        len(report.drift),
    )
    return report


@app.get("/reports/{session_id}", response_model=SessionReport)
def get_report(session_id: str, engine: Engine = Depends(get_engine)) -> SessionReport:
    """Return a stored report, or 404 when the session was never replayed."""
    report = load_report(engine, session_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"no report for session {session_id}")
    return report
