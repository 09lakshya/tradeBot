# ADR 0001 — Modular monolith over microservices

**Status:** Accepted (2026-07-23)

## Context

The spec targets a commercial-grade platform with many subsystems (data, OMS, risk,
strategies, backtest, ML research). A microservices layout is tempting but the team is
small and the domains are still co-evolving.

## Decision

Build a modular monolith: one deployable FastAPI app with strict domain boundaries under
`app/domains/*`, plus Celery workers for async/long-running work. Each domain owns its
models, service, and router.

## Consequences

- (+) One deploy, one DB, simple local dev, no network boundaries to debug early.
- (+) Boundaries drawn so any domain can later be extracted to a service without rewrites.
- (−) Requires discipline to keep domains from importing each other's internals — enforced
  via the order-path contract and code review.

## Alternatives considered

- **Microservices now:** rejected — premature distribution complexity for a solo/early team.
- **Single-file app:** rejected — becomes unmaintainable, violates the "avoid tech debt" goal.
