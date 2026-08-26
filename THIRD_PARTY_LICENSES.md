# Third-Party Licenses

This project is licensed under the [Apache License 2.0](LICENSE). It depends on the following
direct third-party packages, resolved via `pip`/`uv` at install time — none of their source code is
vendored into this repository. Versions are the exact locked versions from `uv.lock` at the time of
this review. All licenses listed are OSI-approved and permissive; none impose copyleft obligations or
are incompatible with distributing this project under Apache-2.0.

## Production dependencies

| Dependency | Version | License | Source |
|---|---|---|---|
| fastapi | 0.141.1 | MIT | https://github.com/fastapi/fastapi |
| jinja2 | 3.1.6 | BSD-3-Clause | https://github.com/pallets/jinja |
| jsonschema | 4.26.0 | MIT | https://github.com/python-jsonschema/jsonschema |
| neo4j | 6.2.0 | Apache-2.0 AND Python-2.0 | https://github.com/neo4j/neo4j-python-driver |
| openai | 3.3.1 | Apache-2.0 | https://github.com/openai/openai-python |
| opentelemetry-proto | 1.44.0 | Apache-2.0 | https://github.com/open-telemetry/opentelemetry-python |
| pydantic | 2.13.4 | MIT | https://github.com/pydantic/pydantic |
| pyyaml | 6.0.3 | MIT | https://pyyaml.org/ |
| uvicorn | 0.52.4 | BSD-3-Clause | https://github.com/encode/uvicorn |

## Development dependencies

| Dependency | Version | License | Source |
|---|---|---|---|
| httpx | 0.28.1 | BSD-3-Clause | https://github.com/encode/httpx |
| pytest | 9.1.1 | MIT | https://docs.pytest.org/ |
| pytest-asyncio | 1.4.0 | Apache-2.0 | https://github.com/pytest-dev/pytest-asyncio |
| ruff | 0.16.4 | MIT | https://docs.astral.sh/ruff |
| testcontainers | 4.15.0 | Apache-2.0 | https://github.com/testcontainers/testcontainers-python |

## Notes

- **neo4j**: the official Neo4j Python driver's declared license expression is `Apache-2.0 AND
  Python-2.0` — both are permissive, OSI-approved licenses; the `Python-2.0` component applies to a
  small amount of code derived from the CPython standard library within the driver, not to this
  project's own code.
- No `NOTICE` file is included in this repository. Apache License 2.0 §4(d) only requires
  redistributing a dependency's `NOTICE` attribution content when that dependency's source is itself
  redistributed (e.g. vendored) as part of a derivative work. This project depends on all of the above
  packages via PyPI at install time and does not vendor or embed any of their source code, so no
  `NOTICE` file is required.
- License data was verified directly against each installed package's metadata (`License-Expression`,
  cross-checked against PyPI `Classifier` entries) in this project's own virtual environment, not
  inferred from package names or assumed.
- This table covers direct dependencies only, as required by the project's Open Source Readiness
  specification. It is not a full transitive dependency license audit.
