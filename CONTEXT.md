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
and carries its enabled switch. An Action node that owns an Automation is
archived, never deleted; one without an Automation owns no Invocations
and is deleted outright.
_Avoid_: Task, step, output

**Archived Action**:
An Action node with an Automation, removed from the Canvas by the user.
It keeps its
identity, settings, Automation and every Invocation forever, and can be
restored to the Canvas with no Edges. Its Invocations keep being
mirrored while archived, so restoring surfaces every metric. Archiving
disables the Automation; restoring does not re-enable it until the Action
is a Flow again.
_Avoid_: Deleted action, tombstone, soft deleted

**Outcome node**:
A node that collects the Invocations of an Action node that ended with one
Outcome kind. Clicking it lists those Invocations.
_Avoid_: PR node, result, sink

**Edge**:
A link between nodes. A Trigger to Action edge carries the count of
Invocations; an Action to Outcome edge carries the count of Invocations
with that Outcome. Both counts are derived from the Action node's
Invocations, an Edge stores nothing of its own, so deleting and redrawing
an Edge is always lossless.
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

### Simulation

**Seed Flow**:
The Flow that `seed` creates when it is missing: a Trigger on the Target
repository's issue opened event, the Action node "Seed: Issue triage"
under a fixed id, and one Outcome node per Outcome kind. Reused, never
recreated, so its Automation is stable across runs.
_Avoid_: Default flow, demo flow, fixture

**Target repository**:
The GitHub repository a manually built Flow triggers on and the Simulator
files issues against. A test bed whose default branch is overwritten on every
Reset.
_Avoid_: Fork, superset, victim

**Simulator**:
The command that resets the Target repository and then files the Scenario's
issues over a short window so a running Flow can be watched end to end.
_Avoid_: Load generator, harness, driver

**Scenario**:
The versioned description of one Simulator run: the Baseline, the Poisoned
bugs, and the ordered list of Simulated issues with their Phase and
expected Outcome.
_Avoid_: Config, plan, fixture

**Baseline**:
The commit of the Target repository that a Reset starts from, pinned by
SHA in the Scenario.
_Avoid_: Tag, snapshot, golden

**Poisoned bug**:
A deliberate defect applied on top of the Baseline by a Reset, paired with
the Simulated issue that reports it. Each one fails exactly one existing
unit test.
_Avoid_: Mutation, injected fault, plant

**Simulated issue**:
One GitHub issue the Simulator files, written in the Target repository's
bug report template, with an expected Outcome. Duplicates reference the
Simulated issue they repeat.
_Avoid_: Ticket, fake issue, event

**Phase**:
The slot of the run window a Simulated issue is filed in: original,
filler or duplicate. Every original precedes every duplicate.
_Avoid_: Stage, bucket, wave

**Reset**:
Returning the Target repository and every non-archived Action connected to a
Trigger for it to the Scenario's start state: sessions terminated, issues and
pull requests removed, default branch set to Baseline plus Poisoned bugs,
Invocations cleared. Users build the Flow on the Canvas first; `uv run seed`
is an optional shortcut.
_Avoid_: Cleanup, rollback, restore
