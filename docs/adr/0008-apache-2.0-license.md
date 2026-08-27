# 8. License under Apache License 2.0

Status: Accepted

## Context

Open-sourcing the project (H5) requires picking a license before any public release — every other
H5 decision (LICENSE file, SPDX identifiers, `THIRD_PARTY_LICENSES.md`, the README's license
section) depends on this one being settled first.

## Decision

Apache License 2.0 (SPDX identifier `Apache-2.0`), full unmodified standard text in `LICENSE`.
Chosen because it:

- permits commercial use, modification, and redistribution,
- permits private use,
- includes an explicit patent grant (Section 3) — not all permissive licenses do,
- is widely used and well understood in infrastructure, cloud, and enterprise projects, which is
  this project's natural adopter base,
- doesn't foreclose a possible future consulting/enterprise offering built around the open-source
  core.

## Consequences

- `LICENSE` must contain the complete, unmodified Apache-2.0 standard text — no substitution of the
  copyright holder placeholder is required by the license itself, since Apache-2.0 doesn't use the
  same "insert copyright line into the license text" pattern as MIT/BSD.
- Every direct dependency's license needs to be Apache-2.0-compatible; `THIRD_PARTY_LICENSES.md`
  documents this per-dependency (name, version, license, source URL, notes) and is a required
  reviewed artifact before each release — see the pull request template's "licensing compatible"
  checkbox.
- A `NOTICE` file was considered and deliberately not added: Apache-2.0 only requires reproducing a
  `NOTICE` file if one exists in a work being redistributed, and this is an original work with no
  upstream `NOTICE` to carry forward or additional attribution notices to add beyond what
  `THIRD_PARTY_LICENSES.md` already documents.
- Source files may optionally carry SPDX license headers; this is not currently enforced
  automatically (no CI check for it).
