---
status: accepted
supersedes: 0001
---

# The Action node owns the Automation

ADR 0001 put `automation_id` and sync state on the Trigger to Action edge,
so removing the edge had to soft delete it to keep the Automation's
identity and history. Because an Action node accepts at most one incoming
Trigger edge, the edge and the Action are one to one, and we moved the
Automation identity to the Action node instead: it is the durable thing on
the Canvas, while the edge only decides whether the Automation is enabled.

## Considered options

- Automation on the edge, edge soft deleted on disconnect (ADR 0001):
  exact counts, but the Automation's identity lives on a link that users
  delete and redraw freely, and reconnecting the same nodes creates a new
  Automation.
- Automation on the Action node, one Trigger per Action (chosen): the same
  counts, because the edge and the Automation are still one to one, and
  the Automation survives disconnecting, redrawing and swapping the
  Trigger.

## Consequences

- `automation_id`, `sync_status`, `sync_error` and `deleted_at` live on
  `action_node`. `edge` is a plain link table and is hard deleted.
- A Flow is an Action node with exactly one incoming Trigger edge. The
  Automation is enabled on the Devin side iff the Action's own enabled
  switch is on and the Action currently has a Trigger. Disconnecting or
  deleting the Trigger disables the Automation and leaves the switch as
  the user set it, so reconnecting restores their choice.
- Connecting a different Trigger reconfigures the same Automation
  (trigger, name and metadata) rather than creating a new one.
- Deleting an Action node soft deletes it and disables its Automation.
  Automations are never deleted from Devin by the Canvas, so
  `automation_id` and Invocation history survive.
- Edits to a connected Trigger or to an Action mark the Action
  `sync_status = pending`; the poller from ADR 0002 pushes the change.
