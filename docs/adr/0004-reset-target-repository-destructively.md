---
status: accepted
---

# Reset the Target repository destructively from a pinned Baseline

The Simulator needs the same start state on every run: no issues, no
pull requests, no running sessions, and a default branch that contains
exactly the Baseline plus the Poisoned bugs. We get there by terminating
non-terminal sessions through the Devin API, hard deleting every issue,
closing every pull request and deleting its branch, and force-pushing the
default branch to Baseline plus the Poisoned bug patches, which live in
this repository next to the Scenario rather than in the Target repository.

## Considered options

- Close issues and pull requests, leave history: cheap, but the triage
  Playbook searches recently closed issues for duplicates, so leftovers
  from the previous run change the expected Outcomes.
- A long-lived poisoned branch in the Target repository: drifts from the
  Baseline, and a Devin fix merged there would silently unpoison the next
  run.
- A dedicated default branch for simulation: keeps `master` intact, but
  the Playbook reproduces against the default branch, so the branch would
  have to be the default anyway.
- Baseline SHA plus patches in this repository, destructive reset
  (chosen): the whole start state is reviewable in one place and derived,
  never accumulated.

## Consequences

- The Target repository is a test bed. Anything on its default branch
  that is not in the Scenario is lost on Reset.
- Reset needs an admin `gh` login on the Target repository: enabling
  Issues, `deleteIssue` (GraphQL), force-push and branch deletion.
- Actions connected to a Trigger for the Target repository are never wiped,
  only their Invocation rows. Users build the Flow on the Canvas before
  resetting.
- Sessions from the previous run are terminated, not awaited. Their work
  is disposable by definition.
