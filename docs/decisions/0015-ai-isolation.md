# ADR 0015 — AI Research Engine isolation from execution

**Status:** Accepted (2026-08-02). Additional decision 4 of the design-package approval.

## Context

The platform's long-term vision is autonomous AI-driven strategy research. The failure mode to prevent is an AI
loop that trades directly — a bug or bad model could then place real orders with no gate. The autonomous vision
is only safe if the AI is structurally incapable of executing.

## Decision

**The AI Research Engine must never directly place orders.** Its responsibilities are limited to strategy
**discovery, optimization, evaluation, and recommendation**. Enforcement is structural, not policy:

- The research domain has **no dependency on and no handle to** the OMS/Execution layer; it cannot call it.
- The **only** output interface is the **strategy registry**, where research writes **candidate** versions.
- The Paper Trading Engine consumes **only approved/promoted** versions (candidate → validated → paper →
  human-approved live). Unapproved versions are not loadable by the OMS.
- Every promotion to live also passes the mandatory Risk gate (ADR 0010) and requires human approval.

Consequently, even a compromised or buggy research loop cannot emit an order.

## Consequences

- (+) Hard safety boundary; the autonomous research loop is a candidate generator, never a trader.
- (+) Clear, auditable promotion pipeline as the single seam between research and trading.
- (−) AI improvements reach production only through the staged promotion + human approval, by design slower;
  accepted as the price of safety.

## References
`docs/design/ai-research-architecture.md` §0/§5, ADR 0010 (risk gate), ADR 0011 (build-last sequencing).
