---
name: testing-devin-proxy
description: Test devin-flow's org-scoped Devin API v3 proxy with a controlled local upstream, including service-token isolation.
---

# Local Devin proxy testing

Use a controlled upstream for approved runtime testing. Keep all test traffic local and use an explicit fake service token.

## Setup

1. Read current configuration and route definitions before starting services. `DEVIN_API_TOKEN` and `DEVIN_ORG_ID` are required. Startup fails without either, so missing configuration is a startup test, not a route-level 503 test.
2. Start a local HTTP stub that records request method, path, query parameters, Authorization header, and body. Configure `DEVIN_API_BASE_URL` to its API v3 base, plus a fake `DEVIN_API_TOKEN` and test `DEVIN_ORG_ID`. Confirm the configured base URL is local before starting the backend.
3. Model the current upstream contract: org-scoped `/organizations/{org_id}/sessions`, pagination parameter `first`, and list envelope `{"items": [...]}`. If the base URL includes `/v3`, account for that prefix in the recorded path. Derive session fields and creation responses from the current client models rather than reusing old v1 fixtures.
4. Restart backend processes after configuration changes because settings and clients may be cached. Inspect `.env` and inherited environment variables for unintended real credentials.
5. For Compose runs, set `DEVIN_API_BASE_URL` in the environment Compose reads. Compose forwards this variable to the backend. The stub URL must be reachable from the container: container localhost is not the host. Confirm the upstream request log receives a request before interpreting proxy results.

## Runtime verification

1. Use `/docs` to locate the current public proxy routes. Expand the operation, click **Try it out**, enter the request, and click **Execute**. Verify actual response status and body against the current contract.
2. Check upstream captures for the configured organization path, exact bearer token, `first` value, and creation payload. Public response success alone does not prove forwarding is correct.
3. Exercise upstream non-2xx, unreachable upstream, and malformed successful responses. Include a controlled error and non-JSON body containing the fake bearer token. Verify public errors are generic and neither the upstream body nor token reaches the client.
4. Test current input boundaries and verify rejected requests do not contact upstream.
5. Build the frontend with the same fake token in its environment and scan generated assets for that token. Capture UI evidence separately from HTTP and upstream logs.

Determine database requirements from current startup wiring. Older versions could start proxy and health routes without Postgres, but that is not a guarantee for later revisions.

## Live tests

`uv run pytest` deselects `live`-marked tests (`-m "not live"` in `addopts`); the mocked suite covers the proxy contract without network. `uv run pytest -m live` runs `backend/tests/devin_flow/devin/test_live.py` against the real API using `DEVIN_API_TOKEN` and `DEVIN_ORG_ID` from the environment (the autouse `devin_env` fixture leaves those untouched for `live` tests) and skips when either is unset. It only lists one session and never creates sessions. Do not add create-session live tests.

## Devin Secrets Needed

None for controlled local testing. Set fake values for the required `DEVIN_API_TOKEN` and `DEVIN_ORG_ID`. Real upstream testing requires separate approval and valid credentials.
