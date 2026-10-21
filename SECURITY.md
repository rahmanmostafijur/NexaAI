# Security policy

## Supported versions

Security fixes are applied to the latest release on the `main` branch.

## Reporting a vulnerability

Please **do not open a public issue** for a security problem.

Report it privately through GitHub: open the repository's **Security** tab and choose
**Report a vulnerability** (private vulnerability reporting). Include:

- what you found and which component it affects (backend API, SQL safety layer, ingestion,
  authentication, frontend, container images),
- steps or a proof of concept to reproduce it,
- the impact you expect and any suggested fix.

You can expect an acknowledgement within a few days. Valid reports are fixed and released as soon
as practical, and reporters are credited unless they prefer to stay anonymous.

## Scope and design notes

The following are part of the security model, so a bypass of any of them is in scope:

- **Text-to-SQL safety:** an AST allow-list validator, a dedicated read-only database role,
  `default_transaction_read_only`, a statement timeout and a row cap.
- **Authentication:** short-lived access tokens, single-use rotating refresh tokens in an
  httpOnly `SameSite=Strict` cookie, reuse detection with server-side revocation, and CSRF
  protection on the cookie endpoints.
- **Document handling:** upload validation (extension, size, file signature, duplicates) and
  tagging of retrieved text as untrusted data to resist prompt injection.
- **Secrets:** production mode refuses default JWT, admin and database-role secrets.

Out of scope: vulnerabilities in third-party services you configure (your LLM provider, your
PostgreSQL or Redis host), denial of service by an authenticated administrator, and findings that
require a deployment that ignores the production checklist in `docs/adoption-guide.md`.

## Hardening checklist for operators

Use `docker-compose.prod.yml`, set strong unique secrets, terminate TLS in front of the frontend,
keep PostgreSQL and Redis off the public network, and rotate any secret that may have been
exposed.
