# Illuminate contributor onboarding

This guide takes a new contributor from a well-defined project task through a
reviewed GitHub pull request (PR).
It also explains how to run Illuminate and verify a change locally. No API
credentials are required for the standard development workflow.

## The contribution workflow

Use one task for one reviewable outcome:

1. Create a task with a clear result and acceptance criteria.
2. Start the task in an isolated branch.
3. Make only the changes needed for that task.
4. Validate the complete change locally.
5. Commit and push the branch.
6. Open a pull request, respond to review, and merge it.
7. Confirm the task is complete and remove the branch.

Avoid combining unrelated fixes in one task or PR. Smaller changes are easier to
review, test, merge, and reverse.

## Create a project task

In the Illuminate Replit project, open **Project tasks** and choose **New task**.
Use an outcome-focused title, not an activity such as “work on the UI.”

Write enough detail that another contributor could complete the task without a
separate explanation. This template is a useful starting point:

```markdown
# <Outcome-focused title>

## What & Why
Who needs this, what problem does it solve, and why does it matter?

## Done looks like
- Observable result or acceptance criterion
- Required validation or user-visible behavior
- Documentation updated where applicable

## Out of scope
- Related work intentionally excluded from this task

## Relevant files
- `path/to/likely/file`
```

Before starting, check the existing task list for duplicates and dependencies.
If another task must land first, record it as a blocker rather than implementing
both outcomes together. Move the task to **In progress** only when work begins.

## Create an isolated branch

Replit project tasks may create an isolated work branch automatically. Confirm
the active branch before editing:

```bash
git status
git branch --show-current
```

If you are working manually, synchronize `main` and create a short, descriptive
branch:

```bash
git switch main
make sync-pre
git switch -c feature/<short-task-name>
```

Use prefixes such as `feature/`, `fix/`, or `docs/`. Never develop directly on
`main`, and do not mix changes from another task into the branch.

## Keep Replit main and GitHub main synchronized

GitHub `origin/main` is the canonical shared history, and the Replit workspace's
local `main` must track it. Synchronization is intentionally separate from app
startup, deployment, and post-merge dependency installation: an unattended
runtime must never publish source changes.

Use these checkpoints:

```bash
make sync-pre       # before task work; fetch and fast-forward only, never push
make sync-publish   # after merge, review, and validation; may push local main
make test-sync-main # exercise the policy against disposable local repositories
```

Both sync modes fetch `origin/main` first and require a clean, checked-out
`main` whose upstream is `origin/main`. Their behavior is:

In Replit, these commands automatically use the existing `GITHUB_KEY` secret for
HTTPS GitHub authentication through a temporary, non-interactive credential
bridge that is removed on exit. Agents must use `make sync-pre` before work and
`make sync-publish` after reviewed merges; never print, inspect, copy, or embed
the secret in a command, remote URL, file, or persistent Git configuration.
Outside Replit, the commands leave normal local Git credential helpers in
control.

- **Equal:** report the shared commit; rerunning is safe.
- **Remote ahead:** fast-forward local `main` without creating a merge commit.
- **Local ahead:** `sync-pre` reports that publishing remains; `sync-publish`
  pushes the reviewed commits without force.
- **Diverged:** stop. Inspect both histories, merge `origin/main` into local
  `main` without rebasing, resolve conflicts deliberately, and validate the
  result before rerunning. The command never discards either side or resolves
  semantic conflicts automatically.
- **Dirty tree or wrong branch:** stop. Commit intended task work on its isolated
  branch or stash it; do not let synchronization absorb unrelated files.
- **Fetch/authentication failure:** stop without changing history. In Replit,
  make sure the existing `GITHUB_KEY` secret is available and authorized for
  this repository; do not retrieve or copy its value. Locally, use your normal
  GitHub credential helper or SSH setup. Never put a token in the remote URL or
  commit credentials.
- **Rejected push:** preserve the local commits. Branch protection, required
  reviews, or required checks may prohibit direct updates; use the repository's
  pull-request workflow and rerun the check after GitHub accepts the change.
  Never bypass protection with a force-push.

Before final integration, fetch again because another task may have merged while
you worked. Review `git status --short` and `git diff --cached`, commit only
intended files, run all applicable validation, merge through the required review
path, then run `make sync-publish` from Replit `main`.

Verify agreement at any time with:

```bash
make sync-pre
test "$(git rev-parse main)" = "$(git rev-parse origin/main)"
git status --short --branch
```

The first command must succeed, the comparison must exit zero, and status should
show a clean `main` tracking `origin/main` with no ahead/behind count.

## Make and validate the change

Read the task's acceptance criteria before editing. Preserve the repository's
existing structure and terminology, and never add generated files, local data,
credentials, or backups to Git.

Use the checks appropriate to the files changed:

```bash
# API tests (after make dev has created api/.venv)
(cd api && .venv/bin/pytest)

# Web production build
(cd web && npm run build)

# Review all changes before committing
git status --short
git diff --check
git diff
```

For user-visible changes, also run Illuminate and exercise the affected flow in
the browser. See [Run Illuminate locally](#run-illuminate-locally) below.
If `api/.venv` does not exist, start the host development workflow once with
`make dev`; it creates the environment and installs the API test dependencies.

## Commit and push

Stage only the files that belong to the task:

```bash
git add path/to/changed-file
git diff --cached
git commit -m "Describe the completed outcome"
git push -u origin HEAD
```

Use a concise, imperative commit subject. Do not use `git add .` without first
checking `git status`, because it can stage unrelated or sensitive files.

## Open the pull request

The upstream repository is hosted on GitHub. After pushing:

1. Open the Illuminate project in GitHub.
2. Choose **Pull requests** → **New pull request**.
3. Select your branch as the source and `main` as the target.
4. Use the project task title as the PR title.
5. In the description, explain the change, how it was validated, and any known
   limitations. Link the project task when a link is available.
6. Review the **Changes** tab yourself before requesting review.
7. Create the PR and assign the appropriate reviewer.

A useful PR description is:

```markdown
## Summary
- What changed
- Why it changed

## Validation
- `command that passed`
- Manual flow checked

## Notes
- Known limitations, follow-up work, or “None”
```

Do not paste secrets, personal data, or private logs into the PR. If the change
includes screenshots, check them for credentials and personal information.

## Review, merge, and close the task

- Keep the branch focused while review is in progress.
- Address review comments with new commits, then rerun checks affected by those
  edits.
- Resolve discussions only after the concern is addressed or agreed upon.
- Merge only when required checks and approvals pass.
- After merge, verify the PR reached `main`, delete the source branch, and mark
  the project task complete.
- Create a separate follow-up task for valid work that is outside the current
  task rather than silently expanding the PR.

## Before you run the application

For the simplest setup, install:

- Docker with Docker Compose
- `make`

Allow about a minute for the initial image build and another minute to seed the
demo graph. Python and Node.js are only required for the optional host-side
development workflow.

> **Keep Illuminate local unless you have hardened it first.** The included
> Neo4j credentials are development defaults. Change `NEO4J_AUTH` in
> `docker-compose.yml` and `NEO4J_PASSWORD` in the API environment together
> before exposing any service beyond localhost.

## Run Illuminate locally

From the repository root:

```bash
make up
```

Docker starts Neo4j, the API, and the web interface in the background. Open:

- Illuminate: http://localhost:8080
- API documentation: http://localhost:8000/docs

The navigation rail should show **Graph**, **Entities**, **People**,
**Artifacts**, **Claims**, **Connectors**, and **Settings**.

To stop Illuminate later without deleting its data:

```bash
make down
```

## Load the demo supplier network

On a first run, or whenever the graph is empty, run:

```bash
make seed
```

This loads the V-22 Osprey (PMA-275) scenario from committed fixtures and works
offline. It normally takes about a minute.

> **Important:** seeding resets and rebuilds the graph. Do not run `make seed`
> against a workspace whose graph you need to preserve. Use `make backup` first
> if you are unsure.

Refresh http://localhost:8080 after the command finishes. If the graph does not
load automatically, open **Settings**, search for the V-22 program under
**Consumer (root)**, select it, and return to **Graph**.

## Verify the application with a first workflow

Use this short tour to confirm the application and demo data are working.

1. **Graph:** Select a node to inspect it and an edge to inspect the
   relationship. Double-click a node to expand its neighborhood. Use **Depth**
   in the top bar to change how far the graph loads, or search for entities,
   people, UEIs, and CAGE codes.
2. **Entities:** Filter the table by name or kind. Open an entity row to review
   its report, supplier tier, identifiers, ownership, sources, and risk
   indicators.
3. **People:** Review sourced roles and tenures. An **interlock** badge marks a
   person connected to more than one entity; **SIM** marks simulated demo data.
4. **Artifacts:** Filter the evidence by kind. Open a title to visit its source,
   or use the view button to inspect the stored contents that support claims.
5. **Claims:** Compare **Staged**, **Committed**, and **Rejected** assertions.
   Open the linked evidence before committing or rejecting a staged claim.
   Authoritative connectors can auto-commit; open-web facts wait for human
   review or a second source.
6. **Connectors:** Review which sources work without credentials and which show
   **Key needed**. You do not need to add a key for this walkthrough.
7. **Settings:** Confirm the demo program under **Consumer (root)**. Leave
   **Writes** on **Ask every time (default)** while learning the product so
   write and destructive statements are previewed for approval.

You have completed the tour when you can move from a supplier in **Graph** to
its entity report, inspect an evidence artifact, and find the related claim.

## Optional connectors and keyless mode

Illuminate's core graph workflow does not require an OpenAI key. In keyless
mode you can:

- browse, search, filter, and expand the graph;
- inspect entities, people, artifacts, and claims;
- use template queries; and
- use sources listed as keyless in **Connectors**.

Without an OpenAI key, free-form chat, generated Cypher, extraction, summaries,
and other model-assisted enrichment are unavailable. Some external data sources
also require their own API credentials.

To add an optional credential:

1. Open **Connectors** in the navigation rail.
2. Choose **Add credential** beside the connector.
3. Paste the credential into the password field and select **Save**.
4. For OpenAI, select **Test** to verify the key.

See [Accounts, keys and credentials](ACCOUNTS.md) for connector availability,
registration links, and operating limits.

### Credential safety

- Never commit API keys, passwords, `.env` files containing secrets, or the
  contents of `api/data/` to source control.
- Enter connector credentials through the application rather than placing them
  in documentation or chat messages.
- Connector credentials are encrypted at rest in `api/data/vault.json`; the
  decryption key is stored separately in `api/data/vault.key`.
- A backup includes both the encrypted vault and its key. Protect backup
  archives as sensitive files.

## Troubleshooting

**The web page does not open**

Run `docker compose ps` and confirm the `web`, `api`, and `neo4j` services are
running. Then retry `make up`. Use `docker compose logs` for service errors.

**The graph is empty**

Run `make seed`, wait for it to finish, and refresh the page. Remember that this
command resets the current graph.

**The graph says “No consumer set”**

Open **Settings**, search under **Consumer (root)**, and select the V-22 program.

**A connector says “Key needed”**

That connector is optional. Continue in keyless mode or follow its registration
link in [Accounts, keys and credentials](ACCOUNTS.md).

**OpenAI features do not work after adding a key**

Open **Connectors** and select **Test** beside OpenAI. Replace the credential if
the test fails.

For all available operational commands, run:

```bash
make help
```

## Application next steps

- Change the **Consumer (root)** to explore the same graph from a different
  program or buying organization.
- Add only the connectors needed for your work, noting their quotas in
  [Accounts, keys and credentials](ACCOUNTS.md).
- Back up the graph and settings with `make backup` before substantial changes;
  see the [backup and restore instructions](../README.md#back-up).
- Developers who need hot reload can use `make dev` and open
  http://localhost:5173. This mode additionally requires Python 3.12 or newer
  and Node.js 20 or newer.