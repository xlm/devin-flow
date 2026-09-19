---
status: accepted
---

# Mirror Devin sessions into Invocation rows by polling

The Devin API has no outbound webhooks or event stream, only inbound
webhook triggers. To show invocation and outcome counts on the canvas we
mirror sessions into an `invocation` table in our own database, refreshed
by a poller inside the FastAPI lifespan (every 60 seconds, plus a manual
refresh), rather than querying Devin live on every canvas load.

## Considered options

- Live queries per canvas load: no storage, but slow, subject to rate
  limits, and history disappears if an Automation is deleted in Devin.
- A separate worker (Celery or similar): more moving parts than a single
  org, single canvas deployment needs.
- In-process poller with a local mirror (chosen).

## Consequences

- The poller lists sessions filtered by known `automation_ids` and
  `created_after` the last successful poll (with a safety margin), then
  re-fetches non-terminal Invocations to update status, `pull_requests`
  and `structured_output`.
- Outcome and pull request buckets are recomputed from the mirrored rows
  on every poll; the Pull Request outcome derives from `pull_requests`,
  the others from `structured_output.outcome`.
- Canvas writes commit locally first and record `sync_status` and
  `sync_error` on the Action node (ADR 0003); the poller retries failed
  Devin syncs, so the canvas is the source of truth and the Devin side
  converges.
