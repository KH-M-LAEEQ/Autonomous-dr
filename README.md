# AutonomousDR

Autonomous multi-cloud disaster recovery: detect a fault, decide what to do about
it, check the cost, get agreement from three independent monitors, act, and explain
itself — in under 60 seconds, across AWS, Azure and GCP.

Final Year Project · Faculty of IT & CS, University of Central Punjab · Fall 2026 –
Spring 2027 · Supervisor: Misbah Naz

Build plan: `docs/plan/AutonomousDR_36_Week_Build_Plan.pdf`. Read the week you are
in before you write code for it.

---

## Start here (30 minutes, once)

**You need:** Docker Desktop (running), Python 3.12+, Node 20+, Git.

```bash
git clone https://github.com/<OWNER>/<REPO>.git autonomous-dr
cd autonomous-dr

cp .env.example .env      # local defaults, no secrets needed
make setup                # venv + python deps + npm install + git hooks
make up                   # Postgres, Redis, InfluxDB in Docker
make migrate              # apply database migrations
make verify               # <- the gate. Everything must pass.
```

Then, in two more terminals:

```bash
make api                  # http://localhost:8000/docs
make web                  # http://localhost:5173
```

Open <http://localhost:5173>. You should see four green dependency rows, the live
implementations of each frozen interface, and a WebSocket that round-trips a test
frame. That page exists purely to tell you whether your machine is set up — if it
is green, you are done, and Week 1 is complete for you.

**No cloud account, API key or credential is needed to run any of this.** Cloud
credentials come in Week 7, after the billing alarm is set. `.env` is gitignored
and a pre-commit hook blocks credential-shaped strings — if it ever fires on you,
it is not being clever, it just saved the project.

### Not on macOS or Linux?

`make` is a convenience, not a requirement. Open the `Makefile` and run the
commands under any target directly — they are ordinary shell commands. On Windows,
Git Bash or WSL2 both work; WSL2 is smoother because Docker volume performance on
native Windows filesystems is poor.

---

## The repo

```
core/          Domain layer. Interfaces, models, config, db, audit, Celery tasks.
               Imports nothing from api/, web/ or ml/. Dependencies point inward.
  interfaces/  THE FROZEN CONTRACT. See "Changing the contract" below.
api/           FastAPI. Routers only — logic lives in core/.
web/           Vite + React + TypeScript + Tailwind dashboard.
ml/            Detectors, evaluation harness, datasets, notebooks.
infra/         docker-compose support, Dockerfiles, Alembic migrations, Terraform.
docs/          ADRs, formulas, API contract, diagrams, results.
corpus/        RAG source documents (Week 15). Fetch scripts committed, PDFs not.
scripts/       Developer tooling. verify.py is the one you will use.
```

Ownership, per the build plan — one role, one person, and the CODEOWNERS file
mirrors it:

| Role | Owns |
| --- | --- |
| BACKEND | `core/`, `api/`, `infra/`, `docker-compose.yml`, CI, deployment, **and Friday integration** |
| FRONTEND | `web/`, `docs/diagrams/`, documentation formatting, report exports |
| AI | `ml/`, `corpus/`, `docs/results/`, `docs/formulas.md`, decision logic, evaluation |

Shared and requiring all three to approve: `core/interfaces/`, `core/models/`,
`docs/adr/`, the database schema.

---

## Working here

Full detail in [CONTRIBUTING.md](CONTRIBUTING.md). The short version:

1. **Branch from `main`, one week maximum.** `git switch -c feat/backend/collector-influx`
2. **Open a PR into `main`.** Never push to `main` — a local hook blocks it too.
3. **CI must be green.** Lint, types, tests, frontend build, secret scan, compose validation.
4. **Merge on Friday**, whether the module is finished or not. Partial work behind a
   flag beats a three-week branch.
5. **`main` always demos.** If `main` cannot run the loop end to end, fixing that
   outranks every other task anyone has.

Before every push:

```bash
make fmt && make lint && make test
```

Same commands CI runs, so a green local run means a green PR.

---

## Changing the contract

`core/interfaces/` and `core/models/` are frozen after the Week 2 design review.
The five interfaces — `CloudProvider`, `AnomalyDetector`, `ConsensusStrategy`,
`ActionExecutor`, `ExplanationEngine` (plus `PricingSource` and
`ThresholdStrategy`, added in ADR-0009) — are what let a 17-week-old plan
absorb a new cloud provider, a new detector or PBFT without a rewrite.

- **Adding an implementation is free and expected.** A new detector is a new class
  satisfying `AnomalyDetector`, selected with `DETECTOR=` in `.env`. No other file
  changes. That is the whole design.
- **Changing a signature requires an ADR** in `docs/adr/`, all three roles
  approving in writing, and the code in the same PR. `core/tests/test_interfaces.py`
  fails on any accidental change — that test is the freeze, mechanically enforced.

Swapping implementations is configuration, not code. `.env` selects the live
detector, consensus strategy, executor, explainer and provider set; the frontend's
"live implementations" panel shows you what is actually running.

---

## When something breaks

| Symptom | Fix |
| --- | --- |
| `make verify` fails on a port | `make up`, then wait ~15s for health checks |
| `pgvector extension absent` | `make nuke && make up && make migrate` (deletes local data) |
| Postgres connects but no tables | `make migrate` |
| API starts, dashboard shows nothing | Is `make api` running? The dashboard proxies to :8000 |
| `ModuleNotFoundError: core` | Activate the venv, or run `pip install -e ".[dev]"` |
| Port 5432 already in use | You have a local Postgres. Stop it, or change `POSTGRES_PORT` in `.env` |
| Pre-commit blocked your commit | Read the message. If it mentions a key, do not `--no-verify` — move it to `.env` |
| CI red, local green | Compare versions: CI uses Python 3.12 and Node 22 |

Still stuck after 20 minutes: post the **output of `make verify`** in the group,
not "it's not working".

`make nuke` destroys the Docker volumes, including collected telemetry. From Week 3
onward the collector runs continuously and that data is the dataset the whole
results chapter depends on — so from Week 3, `make nuke` needs a reason.

---

## Cadence

| When | Length | What |
| --- | --- | --- |
| Monday | 30 min | Read this week's plan section aloud, split tasks, update the board |
| Wednesday | 15 min | Blockers only |
| Friday | 2 h | Merge everything, run the end-to-end demo, tick the week's "Done when", log actual hours |
| Saturday | 20 min | Retrospective: what slipped, does next week need re-cutting |

One rest day a week, actually taken. Week-30 burnout is in the risk register for a
reason.

---

## Reference

- [CONTRIBUTING.md](CONTRIBUTING.md) — git workflow, PR rules, definition of done
- [docs/adr/](docs/adr/) — every architectural decision and why
- [docs/formulas.md](docs/formulas.md) — every formula, with its citation
- [docs/api/](docs/api/) — the frozen OpenAPI contract
- [docs/results/](docs/results/) — every measured number, including the bad ones
- `make help` — every command available
