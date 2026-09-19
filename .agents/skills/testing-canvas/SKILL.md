---
name: testing-canvas
description: Test devin-flow Canvas persistence, connection rules and node-deletion cascades through the browser and local API.
---

# Canvas runtime testing

## Devin Secrets Needed

None for local Canvas-only testing. Settings requires nonempty DEVIN_API_TOKEN
and DEVIN_ORG_ID even when no Devin API call occurs. Supply dummy values to
both Alembic and FastAPI processes. Use real credentials only when testing
actual Devin integration.

## Prepare

1. Follow the repository blueprint database/startup commands. Confirm the
   database revision is current and Vite `/api/health` returns ok.
   When restarting, inspect listening process IDs. Terminating a shell can
   leave FastAPI reloader or Vite children holding the original ports.
2. When the palette is unavailable, seed nodes through `/api/canvas/nodes/{kind}`
   with explicit positions, retaining returned UUIDs and a label-to-ID map.
   Use a dedicated empty local Canvas or preserve unrelated rows.
   Seed at least one edge and leave another compatible pair unconnected.
   Finish when GET matches the intended fixture exactly.

## Browser gestures and assertions

- Use the rendered handle positions. Default Vue Flow nodes can have bottom
  source handles and top target handles, not left/right handles.
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
  a missing node is a 404. Validate the message and the unchanged GET, not
  just a non-2xx response.
- A failed node DELETE makes the frontend reload the whole Canvas from GET
  rather than patch local state. Expect one extra GET, not a local undo.

## Load-error recovery

With persisted nodes present, stop the backend process and confirm its port
is closed while Vite remains available. Reload the frontend and verify an
explicit load-error alert, Retry button, and zero rendered graph nodes/edges.
Restart the real backend against the same database, then click Retry without
reloading the page. Finish when the alert disappears and the persisted graph
returns unchanged. Separately load an empty successful response and verify no
alert, which distinguishes failure from a legitimate empty board.

Observe the page-level API health badge separately from Canvas recovery.
It is checked once on mount (issue #27), so it can still say error after a
successful Canvas retry. Record both states rather than reading the badge
as proof that the Canvas reload failed.
