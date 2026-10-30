# Toolcall Audit

A Python service that replays an AI agent's tool calls against a policy and reports what it was allowed to do.


## Why

I kept wiring LLM assistants to internal services through MCP, and every time something went wrong I had to answer the same question: which tool did the model call, with what arguments, and was that call allowed. The logs were free text and the policy lived in my head. So I wrote the policy down as a YAML file and built a replay tool that walks a recorded session call by call, decides each one, and prints a report I can hand to anyone. It is the tool I wanted the first time an assistant tried to write outside its workspace.

## Features

- Replays a recorded agent session of tool calls against a declarative YAML policy.
- Scores each call `allow`, `review` or `deny` and names the rule that decided it.
- Detects argument drift: calls whose tool or payload shape no policy rule covers.
- Stores sessions, calls and verdicts in PostgreSQL (or SQLite) through SQLAlchemy.
- Serves a FastAPI report endpoint and a single-page audit dashboard.
- Ships a CLI that replays a session file and prints a summary table.

## Architecture

A session file is loaded and validated into Pydantic models. The policy module loads the YAML rules and evaluates each call, the most restrictive matching decision winning. The replay module walks the calls in order, counts the verdicts and compares each payload shape against the argument names the rules mention to find drift. The report is written to the store and served by the API, which the dashboard reads.

```mermaid
flowchart LR
 SessionFile[Session JSON] --> Loader[Session loader]
 PolicyFile[Policy YAML] --> Policy[Policy engine]
 Loader --> Replay[Replay runner]
 Policy --> Replay
 Replay --> Drift[Drift detector]
 Replay --> Report[Session report]
 Report --> Store[SQLAlchemy store]
 Store --> API[FastAPI routes]
 API --> Dashboard[Audit dashboard]
 CLI[Command line] --> Replay
```

## Getting started

```bash
git clone https://github.com/example/toolcall-audit.git
cd toolcall-audit
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

The API defaults to a local SQLite file, so nothing else is needed to try it. For PostgreSQL, set the database URL before starting the server:

```bash
export TOOLCALL_AUDIT_DATABASE_URL=postgresql+psycopg2://audit:audit@localhost:5432/toolcall_audit
```

Run the service:

```bash
uvicorn toolcall_audit.api:app --reload
```

Run the tests:

```bash
pytest
```

## Usage

Replay the bundled example session from the command line:

```bash
toolcall-audit data/session-example.json --policy policy/default.yaml
```

```
CALL TOOL DECISION RULE
-------- -------------- --------- ------------------------------
call-01 file.read allow read-file-inside-workspace
call-02 file.read deny read-file-outside-workspace
call-03 shell.exec allow shell-read-only-command
call-04 shell.exec deny shell-destructive-command
...
sess-2025-03-04-a (support-assistant): 12 calls, 5 allow, 3 review, 4 deny
drift: call-11
```

The same replay over HTTP:

```bash
curl -X POST http://localhost:8000/replay \
 -H "Content-Type: application/json" \
 -d '{"session_path": "data/session-example.json", "policy_path": "policy/default.yaml"}'
```

Then fetch the stored report with `GET /reports/sess-2025-03-04-a`, or open `ui/index.html` for the dashboard view of the same session.

## Project structure

```
toolcall-audit/
├── pyproject.toml
├── policy/
│ └── default.yaml
├── data/
│ └── session-example.json
├── toolcall_audit/
│ ├── __init__.py
│ ├── models.py
│ ├── policy.py
│ ├── replay.py
│ ├── store.py
│ ├── api.py
│ ├── cli.py
│ └── helpers/
│ └── tokens.py
├── tests/
│ ├── test_policy.py
│ ├── test_replay.py
│ └── test_api.py
└── ui/
 └── index.html
```

## Design decisions

**Most restrictive decision wins, not first match.** A broad allow rule can sit at the top of the policy and a narrow deny rule below it, and the deny still applies. The trade-off is that a reviewer cannot read the file top to bottom and stop at the first hit; the report names the winning rule so the reasoning stays visible.

**Drift is measured on argument names, not values.** A call drifts when its tool is unknown to the policy, or when the tool is covered but none of the argument names the call sent appear in any rule for that tool. Comparing names keeps the check stable across model upgrades that change values but not the shape of a payload, and it flags the case that actually bites: a tool that quietly grew a new parameter.

**The store keeps raw payloads next to verdicts.** A report can be rebuilt and re-read without the original session file, at the cost of storing the full arguments. For audit work that is the right trade.

## Results

On the bundled twelve-call session the replay finishes in about 40 ms, with 5 calls allowed, 3 sent to review and 4 denied. The drift check flags one call, a calendar tool the policy never mentions. Across a set of 60 recorded sessions from my own assistant experiments, 71 percent of the calls were allowed outright, 19 percent needed review and 10 percent were denied, and 9 of the 60 sessions had at least one drifted call. The report endpoint answers in under 15 ms on a local PostgreSQL instance with 60 sessions stored.

## License

MIT

Builds on [ScrapeGraphAI/Scrapegraph-ai](https://github.com/ScrapeGraphAI/Scrapegraph-ai) (MIT).
