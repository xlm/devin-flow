# Demo

Run devin-flow from the Docker image, build a triage Flow on the Canvas, then
file issues on the public fork `xlm/superset` and watch Devin triage them.
No fork admin access needed, issues are created by hand through GitHub's UI.

## 1. Build and run

Prerequisites: Docker, a GitHub account, and a Devin org where you have a
service token (Settings -> Service Users) and the GitHub connection's
Automation scope is **All installed repos** (the fork is public).

```sh
git clone https://github.com/xlm/devin-flow && cd devin-flow
cp .env.example .env    # fill in DEVIN_API_TOKEN and DEVIN_ORG_ID
docker compose up --build -d    # postgres, migrations, app on :8000
docker compose run --rm --entrypoint sync-playbooks app   # uploads the Issue triage Playbook
```

Open http://localhost:8000.

## 2. Build the Flow

Drag from the palette and connect the nodes:

1. **Trigger**: repository `xlm/superset`, event `opened`.
2. **Action**: choose Playbook `Issue triage`, connect the Trigger to it,
   click **Enable**. Wait for the node to show `enabled`.
3. **Outcomes**: four nodes connected to the Action, kinds `pull_request`,
   `duplicate`, `not_reproducible`, `not_a_bug`.

## 3. File issues

Create these at https://github.com/xlm/superset/issues/new, in order. Give
Devin a minute between the original bug and its duplicate. The bugs exist
on the fork's `master` because the maintainer has run `simulate-issues
reset` (see `SIMULATOR.md`), ask them to rerun it if the fork looks used.

**Issue 1, a real bug (expect a pull request)**

Title:

```
Relative time filters move in the wrong direction
```

Body:

```
### Bug description
Relative time filters such as `30 seconds ago` move the query window forward instead of backward.

### How to reproduce the bug
1. Open a chart with a time range filter.
2. Use `30 seconds ago` as the range.
3. Compare the generated start time with the current time.

### Additional context
The same behavior affects minutes, hours, days, and quarters when the expression uses `ago`.
```

**Issue 2, a feature request (expect `not_a_bug`, label `enhancement`)**

Title:

```
Add a compact export history panel
```

Body:

```
### Bug description
Please add a compact export history panel to the chart page.

### How to reproduce the bug
This is a product suggestion, not a reproducible bug.

### Additional context
A small panel showing recent exports would make repeated downloads easier to find.
```

**Issue 3, not reproducible (expect `not_reproducible`, label `needs-repro`, closed)**

Title:

```
Dashboard title changes are lost after refresh
```

Body:

```
### Bug description
A dashboard title sometimes appears to revert after refreshing the page.

### How to reproduce the bug
1. Edit a dashboard title.
2. Save the dashboard.
3. Refresh the browser.

### Additional context
I could not reproduce this consistently and have no server logs.
```

**Issue 4, a duplicate of issue 1 (expect `duplicate`, closed)**

Title:

```
Past-relative ranges point after the current time
```

Body:

```
### Bug description
Past-relative ranges are landing on the future side of the selected time.

### How to reproduce the bug
Choose a range expressed as a number of seconds ago and compare it with the current time.

### Additional context
This appears to be the same symptom as another report, but the example uses a different chart.
```

More bugs and duplicates are in `backend/src/devin_flow/simulate/scenario.toml`.

## 4. Watch

Within a poll interval (60s) each issue shows up as an Invocation on the
Action. As sessions finish, the Outcome counts move, and clicking an Outcome
opens its Invocations with links to the Devin session and, for issue 1, the
pull request on the fork. Devin also labels each issue and comments with its
reasoning. Sessions take 15-25 minutes to settle.

Stop with `docker compose down -v`.
