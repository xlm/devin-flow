# Demo

Run devin-flow against your own fork of `xlm/superset`: draw a triage Flow on
the Canvas, let the simulator reset the fork and file eight issues, and watch
Devin triage them.

## Prerequisites

- `uv`, `gh` and Docker.
- A fork of `xlm/superset` under an account you administer, with `gh` logged
  in as that account:

  ```sh
  gh repo fork xlm/superset --clone=false
  gh auth setup-git
  ```

- A Devin org where you have a service token (Settings -> Service Users), the
  fork added to the GitHub connection, and Automations allowed on public
  repos (scope **All installed repos**).

Replace `<you>` below with the GitHub account that owns the fork.

## 1. Build and run

```sh
git clone https://github.com/xlm/devin-flow && cd devin-flow
cp .env.example .env    # fill in DEVIN_API_TOKEN, DEVIN_ORG_ID, SEED_REPOSITORY_FULL_NAME=<you>/superset
uv sync
docker compose up --build -d    # postgres, migrations, app on :8000
```

## 2. Add the Playbook

Uploads `playbooks/issue-triage.md` to your org as the `Issue triage`
Playbook:

```sh
uv run sync-playbooks
```

## 3. Draw the Flow

Open http://localhost:8000 and drag three kinds of node from the palette onto
the Canvas:

1. **Trigger**: repository `<you>/superset`, event **Issue opened**.
2. **Action**: name `Triage superset issues`, Playbook `Issue triage`. Drag an
   edge from the Trigger to the Action, then click **Enable** on the Action
   and wait until it shows `enabled`. This creates the Automation in Devin.
3. **Outcomes**: four nodes, kinds **Pull Request**, **Duplicate**,
   **Not reproducible** and **Not a bug**. Drag an edge from the Action to
   each one.

Every edge matters: the Trigger edge is what lets the Action be enabled, and
each Outcome edge is where the matching verdicts are counted.

## 4. Reset the fork and run

Reset puts the fork in a known state: it deletes its issues, closes pull
requests, deletes non-`master` branches, and force-pushes `master` to the
pinned baseline plus three poisoned backend bugs.

```sh
uv run simulate-issues reset
uv run simulate-issues run --report
```

Issues start appearing on the fork right away, eight over 10 seconds: the
three poisoned bugs, then a feature request and two fake reports, then two
duplicates. Within a poll interval (15s) each shows up as an Invocation on the
Action. As sessions finish, the Outcome counts move, and clicking an Outcome
lists its Invocations with links to the Devin session and, for fixed bugs, the
pull request on the fork. Devin also labels each issue and comments with its
reasoning.

`run --report` then waits for the verdicts and prints expected vs actual:
3 `fixed`, 1 `not_a_bug`, 2 `not_reproducible`, 2 `duplicate`. Sessions take
15-25 minutes to settle. The wait gives up after 45 minutes (`--timeout`,
in seconds) and prints the table with `pending` for issues still running.
`uv run simulate-issues report` re-runs the comparison later.

## 5. Reset and go again

Repeat step 4. `reset` is safe at any point, including mid-run: it terminates
the running sessions of every Action wired to a Trigger for the fork and
clears their Invocations, so the Canvas counts start from zero while the Flow
you drew stays in place.

Stop everything with `docker compose down -v`.
