# 4. Deterministic analyses before generative ones

Status: Accepted

## Context

Architecture questions like "who sends to this queue", "which queues have no known consumer", or
"what's the blast radius of this service" have exact, repeatable answers computable directly from
the graph. Routing every such question through an LLM would make the platform's core value
proposition — a trustworthy architecture knowledge graph — dependent on a non-deterministic,
externally-hosted, potentially-unavailable-or-costly component for questions that don't need one.

## Decision

Five standard analyses (A1-A5: queue senders, queue consumers, senders-without-consumers,
consumers-without-known-senders, mixed sync/async blast radius) are fixed, parameterized Cypher
queries with no LLM involved (`app/analysis/`). The LLM's only role is translating natural-language
questions the fixed analyses don't cover into validated, read-only Cypher, plus a lightweight
deterministic intent router (10C/H3) that recognizes common question shapes and routes them to a
fixed analysis directly, skipping the LLM round-trip entirely when it can.

## Consequences

- The platform's core analytical capability works identically whether or not an LLM provider is
  configured at all — see [0006's](0006-declared-vs-observed.md) sibling principle and
  [configuration.md](../configuration.md)'s LLM-optional guarantee (`llm_provider = None` is a
  supported, tested state, not a degraded one).
- Deterministic analyses are the reliable, cacheable, testable foundation; the LLM layer is
  additive reach into open-ended questions, not a replacement for the graph as source of truth. See
  [0005](0005-llm-is-not-source-of-truth.md).
- New standard analyses (e.g. future Kubernetes-discovery-driven ones) should default to this same
  pattern — a fixed Cypher query in `app/analysis/`, not an LLM prompt — unless the question is
  genuinely open-ended natural language that a fixed query can't parameterize for.
