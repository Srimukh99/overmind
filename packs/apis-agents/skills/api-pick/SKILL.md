---
name: api-pick
description: Use when designing a new API or endpoint, choosing between REST, GraphQL or gRPC, or reviewing an API contract for design and safety.
---

# api-pick

## 1. Choose the style

| If... | Pick |
| --- | --- |
| Many external or partner consumers; HTTP and CDN caching matter; simple per-endpoint limits | REST |
| A few first-party UIs with varied screens; clients over- or under-fetch; frontend teams iterate fast | GraphQL |
| Internal service-to-service, low latency, strong typing, streaming | gRPC |

Record the choice and the reasons as a short decision record.

## 2. Contract first

Write the OpenAPI 3.1 spec or GraphQL SDL, lint it, and get it reviewed before writing handlers. Never ship an endpoint that isn't in the spec.

## 3. Design rules

**REST**: plural nouns, nesting at most two levels, correct status codes, cursor pagination, errors in RFC 9457 problem-details format, ETags for caching and safe concurrent updates.

**GraphQL**: a DataLoader for every resolver that hits a database (no N+1), query depth and cost limits, persisted queries for public clients, Relay-style connections for pagination, mutation payloads that return user errors.

**All styles**:
- Authorization checked per object, not just per route.
- Idempotency keys on requests that create records or move money (`reg-money`).
- Rate limits and request size limits.
- No personal or regulated data in URLs (`reg-phi`, `reg-pci`).
- Additive changes only within a version; deprecate before removing.

## 4. Guard the contract in CI

Fail the build on breaking changes (for example oasdiff for OpenAPI, graphql-inspector for SDL) unless a decision record approves them. Add contract tests and fuzz tests for public APIs.
