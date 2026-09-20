# Issue simulator

`simulate-issues` resets the fork named by `SEED_REPOSITORY_FULL_NAME` to a pinned
baseline plus three poisoned backend bugs, files eight issues over three
minutes, and compares Devin's verdicts with the expected ones. Vocabulary is
in `CONTEXT.md`, the destructive reset is ADR 0004. For a walkthrough that
needs no fork access, see `DEMO.md`.

## Prerequisites

- The stack from `README.md` running, with `uv run sync-playbooks` done so
  the org's `Issue triage` Playbook has the `issue_number` output.
- `gh` logged in with admin on the fork (also used for Git pushes, run
  `gh auth setup-git` if needed):

  ```sh
  gh api "repos/${SEED_REPOSITORY_FULL_NAME}" --jq .permissions.admin   # must print true
  ```

- `SEED_REPOSITORY_FULL_NAME=<owner>/superset` in `.env`, the fork the simulator
  targets (default `xlm/superset`).
- A Flow on the Canvas: Trigger (the configured fork, `opened`) -> enabled Action
  using the `Issue triage` Playbook -> Outcomes `pull_request`, `duplicate`,
  `not_reproducible`, `not_a_bug`. `uv run seed` builds it for you.

## Commands

```sh
uv run simulate-issues reset          # destructive, see below
uv run simulate-issues run --report   # file 8 issues over 180s, then wait for verdicts
uv run simulate-issues report         # rerun the comparison later
```

`reset` refuses unless the Flow above exists. It then terminates running
sessions of every Action wired to a Trigger for the configured fork, deletes all issues,
closes pull requests, deletes non-`master` branches, force-pushes `master` to
baseline + `chore: <poison>` commits, ensures the triage labels, and clears
those Actions' Invocation rows. Safe to rerun at any time, including mid-run.

`run` files, in order: three poisoned bugs (0-60s), a feature request and two
fake reports (60-120s), two duplicates (120-180s). It refuses if `master` is
not at the recorded reset SHA. Expected report: 3 `fixed`, 1 `not_a_bug`,
2 `not_reproducible`, 2 `duplicate`. Sessions settle in 15-25 minutes.

State lives in `~/.cache/devin-flow/superset` (`repo/` checkout,
`.simulate-state.json`, `.simulate-run.json`). To change the mix, copy
`backend/src/devin_flow/simulate/scenario.toml`, edit it, and pass
`--scenario <path>` to `reset` and `run`. The repository defaults to
`SEED_REPOSITORY_FULL_NAME`; an explicit repository in a custom scenario
overrides that setting.
