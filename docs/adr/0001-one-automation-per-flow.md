---
status: superseded by ADR-0003
---

# One Automation per Flow, one Trigger per Flow

A Devin Automation accepts many triggers, so the obvious model is one
Automation per Action node with every linked Trigger inside it. We chose
instead to restrict a Flow to exactly one Trigger node and provision one
Automation per Flow, because the Devin sessions API exposes only
`automation_id` on a session and trigger ids are re-minted on every edit.
Per-edge invocation counts on the canvas are therefore only exact when an
edge and an Automation are the same thing.

## Considered options

- One Automation per Action node with N triggers: fewer Automations in the
  Devin UI, but Trigger to Action edges cannot show individual counts.
- One Automation per Trigger to Action edge, N edges per Action: exact
  counts, but the enabled switch and Automation naming become per-edge
  concerns spread across one Action.
- One Trigger per Flow (chosen): exact counts and the simplest model. A
  user who wants "opened" and "closed" handled the same way draws two
  Flows.

## Consequences

- `automation_id`, sync status and sync errors live on the Trigger to
  Action edge.
- The Automation is disabled, never deleted, when its edge is removed or
  its Flow becomes invalid, so the id and invocation history survive.
- Automations are named `<Action name>: <owner/repo> issue <opened|closed>`
  and carry `metadata` labels pointing back to the canvas ids for
  reconciliation.
