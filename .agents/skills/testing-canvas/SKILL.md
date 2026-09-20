---
name: testing-canvas
description: Test devin-flow Canvas persistence, connection rules, deletion cascades, Outcome invocation sheets, and API/polling status through the browser and local API.
---

# Canvas runtime testing

## Devin Secrets Needed

None for local Canvas-only testing. Settings requires nonempty DEVIN_API_TOKEN
and DEVIN_ORG_ID even when no Devin API call occurs. Supply dummy values to
both Alembic and FastAPI processes. Set POLL_INTERVAL_SECONDS=0 for controlled
invocation fixtures. To avoid live upstream traffic from repository/playbook
dropdowns, set DEVIN_API_BASE_URL=http://127.0.0.1:9. Their load errors are
expected in this isolated configuration. Use real credentials only when
testing actual Devin integration.

## Prepare

Run `pnpm e2e` first. It is the primary verification for Canvas and
FlowCanvas changes. Use the manual steps below only for gestures the suite
does not cover.

1. Follow the repository blueprint database/startup commands. Confirm the
   database revision is current and Vite `/api/health` returns ok.
   Use `docker compose up -d --wait db` before migration on a fresh database.
   Starting the container without waiting can race Postgres initialization.
   When restarting, inspect listening process IDs. Terminating a shell can
   leave FastAPI reloader or Vite children holding the original ports.
2. Create nodes by dragging palette cards onto the Canvas. When the palette
   is unavailable, seed through `/api/canvas/nodes/{kind}` with explicit
   positions. Retain a label-to-ID map. Use a dedicated empty local Canvas
   or preserve unrelated rows. Seed at least one edge and leave another
   compatible pair unconnected. Finish when GET matches the intended fixture.

For fixture-only demos, reload the browser to refresh Canvas counts. The
`Refresh invocations` toolbar button invokes an upstream poll even when the
background poller is disabled. Keep fixture Actions disabled and use direct
local database inserts when no upstream automation creation is permitted.
The seed command currently leaves an empty Canvas, so prepare dedicated nodes
when necessary and remove them along with the temporary Invocation rows.

## Browser gestures and assertions

- Use rendered handle positions. Current custom nodes have left target and
  right source handles. Older default Vue Flow nodes can use top/bottom.
- A target-to-source drag normalizes to source->target. It does not establish
  an invalid reversed direction. Test forbidden kinds with compatible handles,
  such as Trigger source to Outcome target.
- Capture real drags while held, then compare API position/pair data after
  release and after reload. Fit-view may change screen coordinates even when
  saved logical coordinates are unchanged.
- Select an edge or node, then press Backspace. For cascade testing, delete an
  Action with both incoming and outgoing edges. Verify all three records vanish
  after reload and that the interval's access log has one node DELETE and no
  edge DELETEs.
- Check invalid UI attempts before API rejection requests. This keeps a clean
  access-log interval where zero POSTs proves client-side refusal. Compare GET
  after every attempt so a later cleanup cannot conceal a saved invalid edge.
- Read `backend/src/devin_flow/canvas.py` for the connect rules. Every rule
  violation is a 409 with a message, non-finite coordinates are a 422, and
  a missing node is a 404. Validate the message and unchanged GET, not
  just a non-2xx response.
- A failed node DELETE makes the frontend reload the whole Canvas from GET
  rather than patch local state. Expect one extra GET, not a local undo.

## Verifying a FlowCanvas change

The Vitest suite mocks `@vue-flow/core`, so a green frontend gate proves the
component logic and nothing about how Vue Flow renders it. Treat any change
to `FlowCanvas.vue` as unverified until it has run in the real browser.

1. Run `pnpm e2e` (after `pnpm e2e:install` once). It brings up a throwaway
   Postgres, the stub Devin upstream in `frontend/e2e/harness/`, the backend
   and Vite, and runs specs 1-10 against the real Vue Flow renderer. Use
   `pnpm e2e -- --grep "spec 5"` for one spec. Only fall back to the manual
   steps below for gestures the suite does not cover.
2. Populate the Canvas with a configured Trigger connected to an Action that
   has a name and Playbook, matching a real user board rather than empty
   nodes.
3. Repeat the mutating gesture (Refresh, reload, connect, delete) at least
   twice without a page reload. Vue Flow re-validates existing edges
   through `isValidConnection` every time the `edges` prop is replaced, so
   the second render can differ from the first (PR #33 dropped edges on
   alternate Refresh clicks this way).
4. Finish when the rendered graph and its labels match GET after every
   repetition and the console shows no new warnings.

## Outcome fixtures and assertions

1. Connect one Action to three unset Outcomes. Seed four rows directly in the
   local `invocation` table for that Action: PR-only (`outcome: fixed`),
   duplicate-only with `duplicate_of`, both PR and duplicate, and neither.
   Give them distinct titles and `session_created_at` values so newest-first
   sorting and exclusion are observable. Set the neither row newest.
   Read `backend/src/devin_flow/models/invocation.py` for required columns.
   SQL inserts need explicit UUIDs, session/automation/action IDs, status,
   both session timestamps, created_at and updated_at. JSON shapes are
   `pull_requests: [{"pr_url": "...", "pr_state": "merged"}]` and
   `structured_output: {"outcome": "duplicate", "duplicate_of": "..."}`.
   Finish when SQL shows exactly the intended rows for the Action.
2. Use `[data-testid="outcome-kind"]` to choose Pull Request and Duplicate
   on separate nodes. Each must become Ready and its edge change from
   `0 outcomes` to `2 outcomes` without reload. The unset Outcome stays
   Incomplete and zero. After reload, GET `/api/canvas` must contain
   `outcome.kind` values `pull_request`, `duplicate`, null and counts 2/2/0.
   Also verify clearing a kind restores Incomplete and zero.
3. Click the Action->Outcome edge (or its `N outcomes` label), not the
   node, to open the right-side sheet. PR and duplicate sheets each list
   exactly two matching entries newest first. Verify Session hrefs, PR
   hrefs and state badges, and Duplicate of hrefs. The both-match row
   belongs in both lists. The neither row belongs in neither. The unset
   sheet shows `No invocations yet`.
   Relevant selectors: `outcome-invocation`, `outcome-empty`, `outcome-error`,
   `outcome-retry`.
   Clicking a Trigger->Action edge or its `N invocations` label opens the
   action sheet (`action-sheet`, `action-invocation`). Each row leads with
   the triggering issue link, derived from `structured_output.issue_url` or
   a `#N` reference in the session title resolved against the Trigger's
   repository; rows without either show `Issue unknown`.
4. Stop only the backend and confirm its port is closed. Change a saved
   picker value: expect rollback, `Could not save`, unchanged Ready state
   and edge count. Open the sheet: expect `Could not load invocations`.
   Restart the real backend and click Retry without reloading: expect the
   original matching rows and no load-error alert. A subsequent successful
   picker change must clear the save alert and refresh the count.

## Load-error recovery

With persisted nodes present, stop the backend process and confirm its port
is closed while Vite remains available. Reload the frontend and verify an
explicit load-error alert, Retry button, and zero rendered graph nodes/edges.
Restart the real backend against the same database, then click Retry without
reloading the page. Finish when the alert disappears and the persisted graph
returns unchanged. Separately load an empty successful response and verify no
alert, which distinguishes failure from a legitimate empty board.

## API/polling status

The page-level badge (`data-testid="api-status"`, `data-tone`) checks health
every 15 seconds. Canvas Retry and Refresh invocations also refresh health.
Verify visible label and dot color as well as the data attribute.

E2E spec 10 already covers `Polling off`, `API error` after a backend stop,
and recovery through Refresh and Retry. The stack there runs with
`POLL_INTERVAL_SECONDS=0`, so `Polling stale` and `Live` need the manual
steps below.

1. Start with `POLL_INTERVAL_SECONDS=0`. Expect amber `Polling off`.
2. Restart with interval 60, then set `poller_state.last_success_at` to null
   (upsert id 1 if absent). Expect amber `Polling stale` on the next tick.
   An empty Canvas can poll successfully without calling Devin, even with
   dummy credentials. Clear the timestamp after startup and inspect before
   the next backend poll, or configure an owner whose upstream call fails.
3. Set the timestamp to `now()` and click Refresh invocations. Expect green
   `Live`. This fixture proves indicator rendering, not actual Devin sync.
4. Stop the backend and confirm its port is closed. Expect red `API error`
   on the next tick. Restart and keep the page untouched. Expect recovery
   within the next 15-second tick, without a reload.
