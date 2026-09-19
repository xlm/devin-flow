# Devin Flow

A visual editor for Devin automations. Users draw Trigger, Action and
Outcome nodes on a Canvas, link them, and watch how many sessions and pull
requests each link produces.

## Language

### Canvas

**Canvas**:
The single shared board holding every node and edge for one Devin
organisation. There is exactly one Canvas per deployment.
_Avoid_: Board, workspace, diagram

**Flow**:
An Action node with exactly one incoming Trigger edge, optionally linked
on to Outcome nodes. A Flow is the shape that lets the Action node's
Automation be enabled.
_Avoid_: Pipeline, automation, workflow

**Trigger node**:
A node describing one GitHub issue event (opened or closed) in one
repository of the organisation.
_Avoid_: Source, event node, input

**Action node**:
A node describing the Devin session to start: a Playbook plus optional
extra instructions, and a user friendly name. Owns exactly one Automation
and carries its enabled switch.
_Avoid_: Task, step, output

**Outcome node**:
A node that collects the Invocations of an Action node that ended with one
Outcome kind. Clicking it lists those Invocations.
_Avoid_: PR node, result, sink

**Edge**:
A link between nodes. A Trigger to Action edge carries the count of
Invocations; an Action to Outcome edge carries the count of Invocations
with that Outcome.
_Avoid_: Connection, link, wire

### Devin side

**Automation**:
The object on the Devin side that an Action node provisions and keeps in
sync. Identified by its Devin `automation_id`. Never created twice for the
same Action node; disabled rather than deleted. Devin only fires GitHub
Automations on private repos unless the connection's Automation scope is
set to all installed repos (see README prerequisites).
_Avoid_: Flow, job, rule

**Playbook**:
A Devin Playbook, referenced by id from an Action node. The issue triage
procedure (dedupe, classify, reproduce, comment or fix) is one Playbook.
_Avoid_: Prompt template, script

**Invocation**:
One Devin session started by an Automation in response to a Trigger event.
_Avoid_: Run, execution, firing

**Outcome**:
How an Invocation ended, as reported by the session: Pull Request,
Duplicate, Not reproducible or Not a bug. An Invocation with no reported
Outcome belongs to no Outcome node.
_Avoid_: Result, status, verdict
