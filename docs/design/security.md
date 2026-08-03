# Security Review & Design

**Status:** Approved design (design-only) · **Phase:** Design-only · **Depends on:** existing
`app/core/security.py` (JWT HS256, bcrypt, RBAC roles), `config.py` secrets handling, monitoring design.

> Threat model in scope: a self-hosted, cloud-VM trading platform holding financial state and (later) broker
> credentials. Primary assets: the ledger/positions (integrity), broker/API credentials (confidentiality),
> and the order path (availability + authorization). This is a defensive review of the intended controls.

---

## 1. Current state (as built)

`app/core/security.py` provides: bcrypt password hashing (`passlib`), JWT access tokens (HS256) signed with
`settings.secret_key`, and an RBAC `Role` enum (`admin`, `trader`, `viewer`). `config.py` holds secrets via
env/`.env` with full-URL overrides for DB/Redis. This section audits and extends that baseline; nothing below
is implemented in this phase.

**Baseline findings to address at implementation:**
- HS256 is symmetric — fine for a single service; document key-rotation and consider RS256/asymmetric if/when
  tokens are verified by separate services.
- Token creation uses `datetime.now(UTC)` directly. Token *expiry* legitimately tracks wall time, so this is an
  accepted exception to the Clock mandate (which governs *business/trading* time, not auth TTLs) — but note it
  explicitly so it isn't mistaken for a violation.
- No refresh-token / revocation story yet — designed below.

---

## 2. Authentication

- **Users:** bcrypt-hashed passwords (cost factor tuned; `deprecated="auto"` allows rehash-on-verify upgrades).
  Enforce password policy + optional TOTP MFA for `admin`/`trader` (anyone who can move money).
- **Tokens:** short-lived access JWT (minutes) + longer refresh token (stored server-side / rotating) so
  sessions can be **revoked** (logout, compromise). Refresh rotation with reuse-detection.
- **Service/API auth:** machine clients (dashboards, bots) use scoped API keys or client-credential tokens,
  not user passwords; keys are hashed at rest and revocable.
- **Broker credentials (future live):** never user-supplied per request; stored in the secrets manager (§4),
  used only by the broker-integration service behind the `ExecutionVenue` boundary.

## 3. Authorization

- **RBAC** on every mutating route: `viewer` (read-only dashboards), `trader` (submit/cancel orders in own
  portfolios), `admin` (config, risk limits, kill switch, user management). Enforced via FastAPI dependencies,
  default-deny.
- **Object-level authorization:** a trader may act only on **their own** portfolios/orders — checked against
  ownership, not just role (prevents horizontal privilege escalation). The order path verifies
  `portfolio.owner == subject` before accepting.
- **Sensitive controls gated:** kill-switch trip/reset, risk-limit edits, and strategy promotion→live require
  `admin` **and** are audit-logged with actor + reason (§5).
- **Principle of least privilege** for infra: the app's DB role has `INSERT/SELECT` on append-only tables and
  **no `UPDATE`/`DELETE`** on ledger/event tables (defense-in-depth for immutability, per ledger design §7).

## 4. Secrets management

- **No secrets in code or git.** `.env` is gitignored; `.env.example` documents keys without values (already
  the pattern). `secret_key`, DB/Redis URLs, broker creds, provider API keys all come from env/secret store.
- **Production:** a real secrets manager (cloud KMS/Secrets Manager or Vault) injects secrets at deploy;
  the VM never stores long-lived plaintext secrets on disk beyond the process environment.
- **Rotation:** documented rotation for `secret_key` (with a key-id header to allow overlap during rotation),
  DB creds, and provider keys. Rotating `secret_key` invalidates outstanding tokens (acceptable; refresh flow
  re-issues).
- **Least exposure:** provider/broker keys scoped to minimum permissions; separate keys per environment.

## 5. Audit logging

- **Two complementary trails:** (1) the **event store / ledger** is the immutable business audit trail
  (every order, fill, posting, risk decision — already append-only and event-sourced); (2) a **security audit
  log** for auth & admin actions (login success/failure, token issue/revoke, role changes, kill-switch,
  risk-limit edits, secret access) with actor, source IP, `correlation_id`, timestamp, and outcome.
- **Immutable & correlated:** security audit entries are append-only and carry `correlation_id` so a suspicious
  action links to the trading activity it produced. Critical security events alert per the monitoring design.
- **No sensitive payloads:** audit records reference IDs, never raw secrets/tokens/passwords.

## 6. Encryption

- **In transit:** TLS everywhere — client↔API (HTTPS), API↔PG (`sslmode=require`, already supported via the
  cloud URL override), API↔Redis (TLS), and any provider/broker calls. No plaintext transport in production.
- **At rest:** managed-PG storage encryption; secrets in an encrypted store; backups encrypted. Application-
  level field encryption for the most sensitive columns (broker credentials) using envelope encryption with a
  KMS-managed key, so a DB dump alone does not expose them.
- **Passwords/keys:** bcrypt for passwords; API keys stored hashed; never reversible where reversibility isn't
  required.

## 7. API security

- **Input validation:** Pydantic models validate/normalize every request; reject unknown/oversized payloads.
  Money/quantity fields are `Decimal`-typed and range-checked (no float coercion).
- **Injection defense:** SQLAlchemy parameterized queries only (no string-built SQL); output encoding on any
  rendered content.
- **Idempotency:** order submission requires an idempotency key (already an OMS mandate) — also prevents
  duplicate-submit abuse.
- **CORS & headers:** strict CORS allowlist for the frontend origin; security headers (HSTS, X-Content-Type-
  Options, CSP for the Next.js app, no-sniff). No wildcard CORS in production.
- **Error hygiene:** generic error messages externally; details only in correlated server logs (no stack traces
  or SQL to clients).
- **Transport of the WS stream:** authenticated WebSocket (token on connect), authorized to the subject's
  portfolios only.

## 8. Rate limiting & abuse protection

- **Tiered limits:** stricter on auth endpoints (login/refresh — brute-force defense with backoff + lockout),
  and on order submission per user/portfolio (ties to the Risk Engine's churn limits, §3.7 of risk design).
- **Mechanism:** token-bucket in Redis (the market-data layer already uses token-bucket rate limiting — reuse
  the pattern), keyed by user/IP/API-key. Return `429` with `Retry-After`.
- **DoS resilience:** connection/request size caps, slow-loris protection at the reverse proxy, and the
  `/health/ready` gating so an overloaded instance is pulled from rotation rather than accepting doomed work.

## 9. Threats → controls matrix
| Threat | Control |
|---|---|
| Credential theft / brute force | bcrypt, MFA for privileged roles, auth rate-limit + lockout, short tokens + revocation |
| Privilege escalation | default-deny RBAC + object-level ownership checks; admin-only sensitive controls |
| Ledger tampering | append-only + DB `REVOKE UPDATE/DELETE` + reconciliation alerts (integrity, not just access) |
| Secret leakage | secrets manager, no secrets in git, field encryption for broker creds, rotation |
| Injection | parameterized ORM, Pydantic validation, output encoding |
| Data-in-transit interception | TLS everywhere incl. PG/Redis |
| Replay / duplicate orders | idempotency keys, nonce on sensitive ops |
| DoS | rate limits, size caps, readiness-gated shedding, reverse-proxy protections |
| Insider / mistaken destructive action | audit trail + immutability + kill-switch requires reason & is logged |

## 10. Pre-implementation security checklist
1. Add refresh-token + revocation and MFA for privileged roles.
2. Enforce object-level ownership on every order/portfolio route.
3. Provision least-privilege DB roles (no UPDATE/DELETE on append-only tables).
4. Wire secrets manager + rotation runbooks; confirm no secret ever hits logs (formatter redaction).
5. Enable TLS on PG/Redis/broker connections; verify `sslmode=require` end-to-end.
6. Add rate limiting (Redis token-bucket) to auth + order endpoints.
7. Security audit log table + alerts for privileged actions.
8. A dedicated security-review pass (`/security-review`) on the OMS diff before it ships.
