# Operations guide

How to run NexaAI Agent in production: deployment, health checks, metrics, scaling the indexing
queue, backups and restores. For first-time setup and integrating your own data, see
[adoption-guide.md](adoption-guide.md).

## 1. Deploying

```bash
cp .env.example .env     # set the production values below
make up-prod             # or: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The production file layers these changes on the development stack:

| Concern | Production behaviour |
|---|---|
| Ports | Only the frontend (nginx, container port 8080, host `FRONTEND_HOST_PORT`, default 3000) is published. PostgreSQL, Redis and the backend are reachable only on the Docker network. Put a TLS-terminating proxy in front of the frontend. |
| Secrets | Compose refuses to start unless `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET`, `ADMIN_PASSWORD` and `SQL_READONLY_PASSWORD` are set. `ENVIRONMENT=production` makes the application reject default or weak secrets. |
| Indexing | `INGESTION_BACKEND=arq`: uploads are queued in Redis and indexed by the `worker` service, with retries and backoff. |
| Rate limits | `RATE_LIMIT_BACKEND=redis`: one budget shared by every backend replica. |
| Seeding | `SEED_ON_STARTUP=false`: no demo data. |
| Containers | `restart: always`, memory and CPU limits, `no-new-privileges`, dropped Linux capabilities (except PostgreSQL), a read-only filesystem for the frontend, and a health check on every service. The frontend starts only after the backend reports ready. |
| Images | Every image is pinned to a version tag. The frontend runs nginx as a non-root user. |

Session cookies are `Secure` in production, so browsers only send them over HTTPS (browsers
treat `localhost` as secure, so a local smoke test works). Terminate TLS in front of the frontend,
or set `COOKIE_SECURE=false` only for a plain-HTTP internal test.

The backend and worker share the `backend_data` volume for uploaded files, so they must run on
the same host. Spreading them across machines needs object storage, which is not built in.

## 2. Health and readiness

| Endpoint | Meaning | Use for |
|---|---|---|
| `GET /api/health` | The process is up (always 200 while it runs). | Liveness probes, restart decisions |
| `GET /api/ready` | Database reachable, schema at the newest migration, Redis reachable when `REDIS_URL` is set. 503 otherwise. | Load balancer and compose health checks |

The worker publishes its own heartbeat; `python -m arq app.worker.WorkerSettings --check` exits
non-zero when it is missing (this is the worker's compose health check).

## 3. Metrics

Prometheus metrics are served at `/metrics`, outside `/api`, so the bundled nginx never exposes
them. Scrape the backend over the Docker network.

- With `METRICS_TOKEN` set, requests need `Authorization: Bearer <token>`.
- Without a token only direct loopback/private callers are served, and any request carrying an
  `X-Forwarded-For` header is refused.
- `METRICS_ENABLED=false` removes the endpoint.

| Metric | Labels | Meaning |
|---|---|---|
| `nexa_http_request_duration_seconds` | method, route (template), status | Latency until the response starts (streams keep running afterwards) |
| `nexa_agent_runs_total` | route, status | Agent runs by route (`SQL`, `RAG`, `HYBRID`, `GENERAL`, `unknown`) and outcome |
| `nexa_agent_run_duration_seconds` | route | End-to-end run time |
| `nexa_tool_duration_seconds` | tool (`sql`, `rag`, `general`), status | Time in each tool, which covers Text-to-SQL and retrieval |
| `nexa_llm_tokens_total` | type (`prompt`, `completion`) | Language-model tokens consumed |
| `nexa_ingestion_jobs_total` | outcome (`indexed`, `retry`, `failed`) | Indexing attempts |

Logs are JSON on stdout with a request id on every line; secrets are redacted.

## 4. Scaling and the indexing queue

- **API:** stateless apart from the shared database and Redis, so run several replicas behind the
  proxy. Sessions are stored in PostgreSQL and rate limits in Redis.
- **Indexing:** run more `worker` replicas (`docker compose ... up -d --scale worker=3`) to index
  documents in parallel. A job is retried with exponential backoff (`INGESTION_MAX_ATTEMPTS`,
  `INGESTION_RETRY_BASE_SECONDS`).
- **Crashes:** a document left `pending` or `processing` with no progress for
  `INGESTION_STUCK_TIMEOUT_SECONDS` is re-queued by the API's periodic sweep, and marked `failed`
  once it has used all its attempts. Use **Re-index** on a failed document to try again.
- **Migrations:** the backend applies them at start. When starting several replicas for the first
  time, bring up one first so they do not migrate concurrently.

## 5. Backups and restores

Scripts live in [`ops/`](../ops) and work against the compose stack. For production prefix them
with `COMPOSE_CMD="docker compose -f docker-compose.yml -f docker-compose.prod.yml"`.

### Back up

```bash
./ops/backup.sh                 # writes ./backups/nexa-db-<UTC>.dump and nexa-uploads-<UTC>.tar.gz
BACKUP_DIR=/mnt/backups RETENTION_DAYS=30 ./ops/backup.sh
```

The database is dumped with `pg_dump --format=custom` (schema, data, grants). The archive is
listed back with `pg_restore --list` before the script reports success, a failed dump never
replaces a good file, and old backups are deleted after `RETENTION_DAYS` (default 14). Uploaded
documents are archived separately. Redis holds only queue state and counters and is not backed up.

Schedule it, for example with cron: `15 2 * * * cd /srv/nexa && ./ops/backup.sh`. Copy the files
off the host; a backup that lives only next to the database is not a backup.

### Prove a backup restores

```bash
./ops/verify-restore.sh                       # newest dump
./ops/verify-restore.sh backups/nexa-db-<stamp>.dump
```

This restores the archive into a scratch database (`nexa_restore_check`), compares row counts of
the key tables with the live database, and drops the scratch database. It never touches live
data and exits non-zero on a mismatch, so it is safe to run on a schedule (for example weekly).

### Restore

```bash
# 1. Inspect a backup safely, in a separate database named nexa_restore
./ops/restore.sh backups/nexa-db-<stamp>.dump

# 2. Replace the live database (stop the application first)
docker compose stop backend worker
SQL_READONLY_PASSWORD=<the application's value> CONFIRM=yes \
  ./ops/restore.sh backups/nexa-db-<stamp>.dump --replace \
  --uploads backups/nexa-uploads-<stamp>.tar.gz
docker compose up -d backend worker      # applies any migrations newer than the backup
```

`--replace` drops and recreates the live database, so it refuses to run without `CONFIRM=yes`.
The archive carries the table grants for the read-only SQL role but PostgreSQL stores roles per
server, not per database; on a new server the script creates the role first, with the same
settings as migration `0001`, using `SQL_READONLY_PASSWORD` (it refuses to continue without it).

### Tested procedure

The procedure was exercised end to end on a brand-new PostgreSQL server: `restore.sh --replace`
onto an empty cluster, then `alembic upgrade head` to migrate the older backup forward. All
tables came back with identical row counts (950 orders, 8 documents, 4 users in the demo data),
the read-only role could `SELECT` from `commerce` but could not write or read application tables,
and running without `SQL_READONLY_PASSWORD` was refused. Repeat that drill on your own data
before you depend on it.

## 6. Upgrading

1. `./ops/backup.sh`
2. `git pull` and `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
3. Watch `GET /api/ready`; it turns 200 once migrations are applied.

To roll back a release, restore the pre-upgrade backup with `--replace` and start the previous
image tag (`NEXA_IMAGE_TAG`).
