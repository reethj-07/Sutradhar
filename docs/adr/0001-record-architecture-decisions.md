# ADR-0001: Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-06-26

## Context

Sutradhar is a portfolio-grade system meant to surface defensible
system-design stories in interviews (PRD §2). The *reasons* behind key
trade-offs matter as much as the code, and the PRD (§15, NFR7) calls for ADRs.

## Decision

We keep lightweight Architecture Decision Records in `docs/adr/`, one file per
decision, in the [Nygard format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
Each records context, the decision, and consequences. ADRs are immutable once
accepted; a later ADR supersedes an earlier one rather than editing it.

## Consequences

- Every non-obvious choice (model placement, transport default, async design) is
  traceable to its rationale.
- Reviewers can audit the thinking, not just the result.
