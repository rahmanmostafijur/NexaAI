# Production audit

Baseline taken from `main` (commit `9d1ed8c`) before the `production-hardening` branch.

**Baseline results**

| Check | Result |
|---|---|
| Backend `ruff check` / `ruff format --check` | pass |
| Backend `mypy app` | **8 errors** (fails) |
| Backend `pytest` | 169 passed, **48 skipped** with the default `.env` (database unreachable because host port 5434 is shared with other local projects); 217 passed against a reachable database |
| Frontend `tsc`, `vite build` | pass |
| Frontend `vitest` | 32 passed; one run reported errors (flaky) |
| CI / pre-commit / LICENSE / SECURITY / Dependabot | none present |

Severity: **CRITICAL** blocks a launch, **IMPORTANT** should be fixed before launch,
**IMPROVEMENT** raises quality, **OPTIONAL** is nice to have.

The status column is updated as the branch progresses (`open`, `done`, `skipped`).

## Findings

| # | Sev | Area | Finding | Why it matters | Phase | Status |
|---|---|---|---|---|---|---|
| 1 | CRITICAL | Auth | JWT access token (12 h) is stored in `localStorage` and sent as a bearer header. | Any XSS can exfiltrate a long-lived token; there is no way to revoke it. | 1.3 | open |
| 2 | CRITICAL | Auth | No refresh tokens, no server-side revocation, no logout endpoint, no change-password endpoint. | A leaked token stays valid until it expires; account recovery is impossible. | 1.3 | open |
| 3 | CRITICAL | Ingestion | Indexing runs in FastAPI `BackgroundTasks`. A restart or crash leaves documents in `pending`/`processing` forever (and re-index refuses `processing`). | Documents get permanently stuck; no retry. | 1.4 | open |
| 4 | CRITICAL | Config | The read-only SQL role password has an insecure built-in default and production mode does not reject it. | The least-privilege role is only as strong as its password. | 1.3 | open |
| 5 | IMPORTANT | Ops | Postgres port is published by the only compose file; images use floating tags (`pgvector:pg16`, `ollama:latest`); no Redis; no resource limits; frontend does not wait for a healthy backend. | Database exposed on the host; non-reproducible builds. | 1.6 | open |
| 6 | IMPORTANT | Ops | `/api/health` is the only probe and reports DB only; no readiness check (migrations at head, Redis). | Orchestrators route traffic to instances that are not ready. | 1.7 | open |
| 7 | IMPORTANT | Scaling | Rate limiter is in-process. | Limits multiply per replica and reset on restart. | 1.5 | open |
| 8 | IMPORTANT | Dev env | Default Postgres port 5434 collides with other projects; tests skip silently when the database is unreachable. | A "green" run can test nothing. | 1.1 | open |
| 9 | IMPORTANT | Tests | Flaky frontend test run (errors on first run, clean on rerun). | Flaky CI erodes trust. | 1.2 | open |
| 10 | IMPORTANT | Quality | `mypy` reports 8 errors. | CI cannot gate on type checking. | 1.1 | open |
| 11 | IMPORTANT | CI | No CI workflow, Dependabot, pre-commit. | Regressions and vulnerable dependencies go unnoticed. | 2.1-2.3 | open |
| 12 | IMPORTANT | Ops | No metrics endpoint; no graceful shutdown handling for open SSE streams. | Cannot monitor or drain safely. | 2.5, 2.7 | open |
| 13 | IMPORTANT | Ops | No documented, tested backup/restore. | Data loss risk. | 2.6 | open |
| 14 | IMPORTANT | Security | nginx runs as root in the frontend image; uvicorn trusts `X-Forwarded-For` from `*`. | Larger blast radius; spoofable client IP for rate limits when the backend is reachable directly. | 1.6 | open |
| 15 | IMPROVEMENT | Legal | No LICENSE or SECURITY.md. | Reuse terms and vulnerability reporting are undefined. | 2.4 | open |
| 16 | IMPROVEMENT | Features | README roadmap: CSV export, charts, cross-encoder reranker, LLM-as-judge, OpenTelemetry, calculation tool, row-level security. | Planned scope. | 3 | open |
| 17 | IMPROVEMENT | Docs | Docs describe localStorage bearer auth and port 5434. | Must match the code after changes. | 4 | open |
| 18 | OPTIONAL | Tools | `API_TOOL` and `WEB_SEARCH` tools. | Outbound network access from the agent is a new attack surface. | 3.6 | open |

## Already in place (verified, not changed)

- SQL validator (sqlglot AST allow-list), dedicated read-only role with `statement_timeout`,
  `default_transaction_read_only`, row cap, correction loop.
- Prompt-injection tagging of retrieved chunks; upload checks (extension, size, magic bytes,
  duplicate checksum, bounded read).
- Production refusal of the default JWT secret and default admin password.
- Request-id middleware, secret redaction in logs, JSON log formatter, security headers, CSP in nginx.
- bcrypt password hashing with timing-equalised login for unknown users.
