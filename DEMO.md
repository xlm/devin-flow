# Demo: triaging simulated Superset issues

A scripted demonstration of devin-flow against the disposable fork
`xlm/superset`. You build the Flow by hand on the Canvas, the Issue simulator
resets the fork and files eight issues over three minutes, and Devin triages
them while you watch the Invocation counts climb. Vocabulary is in
`CONTEXT.md`, the destructive-reset trade-off is ADR 0004.

## What the audience sees

1. An empty Canvas becomes a Flow: Trigger (issue opened on `xlm/superset`)
   -> Action (Playbook `Issue triage`) -> four Outcomes.
2. Eight issues appear on the fork in three phases: three real bugs, then a
   feature request and two plausible but fake reports, then two duplicates.
3. Devin labels each issue (`bug`, `enhancement`/`question`, `needs-repro`,
   `duplicate`), closes duplicates and unreproducible reports, and opens a
   pull request for each real bug.
4. `report` prints expected vs. actual for the eight issues and exits 0.

Sessions take roughly 15-25 minutes to settle after the last issue is filed,
so start the run early or fill the wait with the Canvas and the fork.

## Prerequisites

- Docker, `uv`, Node 24 + pnpm (see `README.md`).
- `gh` logged in as an account with admin on `xlm/superset`:

  ```sh
  gh auth status
  gh api repos/xlm/superset --jq .permissions.admin   # must print true
  ```

- A Devin service token and org id, and the GitHub connection's Automation
  scope set to **All installed repos** (the fork is public, see `README.md`).
- `.env` in the repo root:

  ```
  DATABASE_URL=postgresql+psycopg://devin:devin@localhost:5432/devin_flow
  DEVIN_API_TOKEN=<service token>
  DEVIN_ORG_ID=<org id>
  SEED_REPOSITORY_FULL_NAME=xlm/superset
  ```

## 1. Start the stack

```sh
uv sync && pnpm install
docker compose up -d db
uv run alembic -c backend/alembic.ini upgrade head
uv run sync-playbooks          # upserts playbooks/ to the org, including Issue triage
uv run fastapi dev backend/src/devin_flow/main.py   # :8000, keep running
pnpm dev                       # :5173, keep running
```

`sync-playbooks` matters: reset refuses to run until the org's `Issue triage`
Playbook has the `issue_number` structured output that `report` uses to match
sessions to issues.

## 2. Build the Flow on the Canvas

Open http://localhost:5173 and drag from the palette:

1. **Trigger**: pick repository `xlm/superset` and event `opened`.
2. **Action**: name it (for example `Issue triage`), choose the `Issue triage`
   Playbook, connect the Trigger to it, then click **Enable**. The node
   shows `enabled` once Devin has provisioned the Automation.
3. **Outcomes**: add four Outcome nodes, connect each to the Action, and set
   their kinds to `pull_request`, `duplicate`, `not_reproducible` and
   `not_a_bug`.

Reset only touches Actions wired to a Trigger for `xlm/superset`, so anything
else on the Canvas is left alone. If you would rather skip the drawing,
`uv run seed` creates the same Flow under the name `Seed: Issue triage`.

## 3. Reset the fork

```sh
uv run simulate-issues reset
```

This terminates any running sessions of the Flow's Automations, enables
Issues and the triage labels on the fork, deletes every issue, closes open
pull requests, deletes every non-`master` branch, force-pushes `master` to
the pinned baseline plus three poison commits (`chore: date-parser-offset`,
`chore: email-attachment-default`, `chore: sql-identifier-quotes`), and clears
the Flow's Invocation rows. It prints the reset SHA at the end. Safe to rerun
at any point, including mid-run.

## 4. Run and watch

```sh
uv run simulate-issues run --report
```

- 0-60s: three poisoned bug reports.
- 60-120s: one feature request, two fake bugs.
- 120-180s: two duplicates of the first phase.

Show the fork's issue list filling up next to the Canvas: the Action's
Invocation count reaches 8 within a poll interval of each issue, and the
Outcome counts move as sessions finish. Click an Outcome node to open its
Invocations sheet with links to the Devin sessions and the fork's pull
requests.

`report` waits for a verdict per issue and prints a table. Expected:
3 `fixed`, 1 `not_a_bug`, 2 `not_reproducible`, 2 `duplicate`. To rerun the
report alone later:

```sh
uv run simulate-issues report
```

## Running it again

Repeat steps 3 and 4. The Canvas, its Automations and the Devin sessions are
kept, only the fork and the Flow's Invocations are reset. To change the mix,
copy `backend/src/devin_flow/simulate/scenario.toml`, edit it, and pass
`--scenario <path>` to `reset` and `run`.
