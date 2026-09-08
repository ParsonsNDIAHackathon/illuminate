# End-to-End Mission Exploratory QA

Date: 2026-09-08  
Workspace revision at test start: `ac904d8`  
Primary environment: Replit workspace, configured workflow `UC7 Illuminate`  
Fallback test environment: disposable local Neo4j data under `/tmp`, offline deterministic seed, API on port 8000, Vite on port 8080  
Published environment: `https://illuminate.furgerson.org` (password protected)

## Executive result

The complete mission path passed against an isolated deterministic fixture:

1. mission readiness and program selection;
2. supply-chain illumination and a guided country preset;
3. live vendor report and risk assessment;
4. trustworthy-versus-risky frozen comparison;
5. committed claim and artifact inspection;
6. versioned CSV findings export; and
7. NDIA event 3 preview and validation-only dry run.

The configured Replit workflow was initially blocked before startup because its existing Neo4j data had a password marker but no protected local credential file. This was reported as a **high-severity environment defect** because a judge opening the development preview could not begin the mission. The test did not reset or replace that graph. A disposable Neo4j instance was used to continue safely. After `NEO4J_PASSWORD` was configured in the environment, the real workflow started and the complete path passed against its persisted graph.

No live NDIA publication was attempted. The dry run returned `validated_dry_run`, and subsequent catalog status remained `not_submitted`.

## Mission charters

### Charter A — primary judge workflow

**Purpose:** Follow the intended decision journey from the mission page to a controlled downstream result.

1. Open `/` in a clean browser session.
2. Confirm readiness, current freshness, and the V-22 program in scope.
3. Open the supply-exposure guided action.
4. Confirm the graph is focused on the mission root and visibly marks simulation content.
5. Open a vendor report, inspect the risk tab, and distinguish evidence-backed factors from missing categories.
6. Load the judged comparison and distinguish the trustworthy and risky profiles.
7. Inspect committed claims and evidence artifacts.
8. Download the findings CSV and verify it is non-empty.
9. Open Settings, review the event 3 catalog metadata, and run only the validation dry run.
10. Confirm no remote submission was recorded.

**Oracle:** Every transition is reachable, truth and simulation labels remain visible, evidence gaps are not presented as clear results, exported findings retain review state, and dry-run behavior performs no publication.

### Charter B — alternate navigation and deep links

**Purpose:** Verify that an analyst can enter the journey from global navigation or a copied deep link.

Test these history-mode routes in clean sessions and then in one reused browser profile:

- `/`
- `/explorer?mission=Supply%20exposure&template=manufactures_in&root_id=ent_6484d4d13b76&country=CN&min_tier=2`
- `/entities/ent_8e865930d2f5?tab=risk`
- `/compare/vendors?preset=judged`
- `/claims?status=committed`
- `/artifacts`
- `/settings`

**Oracle:** The intended view renders directly, not a server 404; the mission context is retained where applicable; routes do not require visiting the home page first.

### Charter C — interrupted and reused session

**Purpose:** Exercise an API interruption without clearing the analyst's browser profile.

1. Navigate through mission, graph, report, comparison, claims, artifacts, and settings using one Chromium profile.
2. Stop the disposable API while keeping the same browser profile.
3. Reload the mission page and confirm it renders `Readiness check unavailable`.
4. Restart the API without reseeding.
5. Reload again in the same profile and confirm `Mission ready`.
6. Confirm catalog state is still `not_submitted`.

**Oracle:** The UI describes the interruption instead of presenting false readiness, and the mission recovers after the API returns without a data reset or catalog side effect.

### Charter D — truth-status transitions and decision safety

**Purpose:** Confirm that analysts can distinguish current, stale, incomplete, risky, trustworthy, and simulated material.

- Current/live: mission health reported current freshness.
- Trustworthy: frozen Atlas Precision Systems profile, score 0, current, 100% complete.
- Risky: live SUBARU CORPORATION profile, score 50/high; frozen Vanguard profile, score 100/critical.
- Incomplete: live SUBARU profile displayed 3/7 categories covered and 43% completeness.
- Stale: frozen Vanguard adverse-media evidence displayed a stale-evidence refresh warning.
- Simulated: graph banner and comparison chips explicitly labeled calibration content as simulated.
- Missing: report categories stated that absent approved evidence is not treated as a clear result.
- Reviewed: committed claims remained queryable and findings export preserved truth-state fields in contract tests.

**Oracle:** Missing or stale evidence never becomes an unqualified clear result; simulated evidence is conspicuous; risk scores remain decision-support signals rather than allegations.

### Charter E — publication boundary

**Purpose:** Validate interoperability without performing an external write.

1. Request `/api/catalog/ndia/preview`.
2. Verify event ID 3 and schema validity.
3. Submit the exact confirmation token with `dry_run: true`.
4. Verify `validated_dry_run`.
5. Request catalog status and verify `not_submitted`.

**Oracle:** Validation succeeds without an operator token, remote dataset ID, or persisted submitted state. Live publication is not attempted.

## Journey evidence

| Area | Result | Evidence |
| --- | --- | --- |
| Mission start | Pass on disposable fixture; initial configured-workflow blocker closed on retest | `qa-evidence/task-29-mission-ready.jpg`, `qa-evidence/task-29-mission-api-unavailable.jpg` |
| Illumination | Pass; 106 nodes and 156 relationships at depth 2; guided CN preset returned one row | `qa-evidence/task-29-illumination.jpg`, `qa-evidence/task-29-live-journey.json` |
| Vendor assessment | Pass; live high-risk/incomplete profile visibly separates verified and missing categories | `qa-evidence/task-29-risky-incomplete-report.jpg` |
| Comparison | Pass; trustworthy and critical-risk profiles align by category and retain simulation/stale labels | `qa-evidence/task-29-frozen-comparison.jpg` |
| Evidence inspection | Pass; 424 committed claims and 181 artifacts returned; claims and artifact routes rendered in clean and reused sessions | `qa-evidence/task-29-live-journey.json` |
| Export | Pass; CSV response contained 100 findings and `text/csv` content type | `qa-evidence/task-29-live-journey.json` |
| Catalog dry-run | Pass; schema valid, event 3, `validated_dry_run`, later status `not_submitted` | `qa-evidence/task-29-catalog-dry-run.jpg`, `qa-evidence/task-29-live-journey.json` |
| Production access | Conditional; unauthenticated users receive the Replit private-deployment gate | `qa-evidence/task-29-production-protection.png` |
| Interruption/recovery | Pass on reused profile; unavailable state appeared while API was stopped and mission-ready returned after restart | `qa-evidence/task-29-live-journey.json` |

## Scenario matrix

| Scenario | Fixture/path | Expected | Actual | Result |
| --- | --- | --- | --- | --- |
| Trustworthy | Judged comparison / Atlas Precision Systems | Current, high-confidence profile with no diligence gaps | Score 0, current, 96% confidence, 100% complete, no gaps | Pass |
| Risky | Live SUBARU report and judged Vanguard profile | Risk is prominent but framed as review support | SUBARU score 50/high; Vanguard score 100/critical with hold-and-escalate disposition | Pass |
| Incomplete | Live SUBARU report | Missing categories reduce completeness and do not become clear findings | 3/7 covered, 43% complete; financial, legal, cyber, and adverse media marked missing | Pass |
| Stale | Judged Vanguard profile | Stale evidence requires refresh before a final decision | Adverse-media gap explicitly says evidence is stale and must be refreshed | Pass |
| Simulated | Guided graph and judged comparison | Calibration content is not presented as allegation or verified fact | Page-level simulation banner plus per-profile and per-evidence labels | Pass |
| Interrupted | Reused profile with API stopped and restarted | Honest unavailable state followed by recovery | `Readiness check unavailable`, then `Mission ready`; no reseed required | Pass |

## Defects

### E2E-001 — Configured Replit workflow could not start with existing Neo4j data

- **Severity:** High
- **Reproducibility:** 2/2
- **Affected environment:** Replit development workspace; configured workflow `UC7 Illuminate`
- **Scope:** Entire judge journey
- **Likely regression area:** Local Neo4j credential migration/bootstrap in `scripts/replit-dev.sh`

**Reproduction**

1. Use the existing workspace state containing `.neo4j/.password-set`.
2. Confirm `.neo4j/dev-password` is absent.
3. Restart `UC7 Illuminate`, or run `scripts/replit-dev.sh`.
4. Observe exit code 1 before Neo4j, API, or Vite opens its configured port.

**Expected**

The configured workflow starts the existing development graph, reaches `/api/health`, and serves the preview. If operator input is required, the workspace should provide a safe, documented recovery path before the judge session.

**Actual**

Startup exits immediately:

```text
Existing Neo4j data needs its current NEO4J_PASSWORD once to create the protected local credential file.
```

The development domain returned HTTP 502, so mission start, illumination, reports, evidence, export, and catalog UI were unavailable through the configured workflow.

**Evidence**

- `qa-evidence/task-29-workflow-startup.log`
- `qa-evidence/task-29-mission-api-unavailable.jpg`

**Retest**

Closed after `NEO4J_PASSWORD` was configured through the environment secret flow. The persisted graph was not reset.

- Managed workflow restart: passed
- Workflow status: running
- `/api/health`: primary workflow ready, current freshness, 862 nodes, 1,809 relationships
- Mission graph: 106 nodes at depth 2
- Guided CN preset: passed
- Vendor report: passed
- Evidence inspection: 450 committed claims and 199 artifacts
- Findings CSV: 100 rows
- Catalog UI/API dry run: `validated_dry_run`
- Catalog state after dry run: `not_submitted`

### E2E-002 — Global app startup rejects an API outage as an unhandled Vue error

- **Severity:** Low
- **Reproducibility:** 2/2 while Vite was running without the API
- **Affected environment:** Development frontend with API unavailable
- **Scope:** Browser diagnostics and outage recovery
- **Likely regression area:** Global startup error handling around workspace loading in `web/src/App.vue`

**Reproduction**

1. Start Vite on port 8080 without an API on port 8000.
2. Open `/` or `/compare/vendors?preset=judged`.
3. Inspect the browser console.

**Expected**

Connection failures are handled by visible page state and do not produce an unhandled mounted-hook rejection.

**Actual**

The mission page correctly rendered its unavailable state, and the frozen comparison still rendered, but the console reported:

```text
Failed to load resource: the server responded with a status of 500 (Internal Server Error)
[Vue warn]: Unhandled error during execution of mounted hook
  at <App>
```

**Evidence**

- `qa-evidence/task-29-browser-console.log`
- `qa-evidence/task-29-mission-api-unavailable.jpg`

**Retest**

Open. After the API started, the mission page rendered cleanly and the same reused profile recovered.

## Environment observations, not product defects

- The published deployment is password protected. An unauthenticated judge sees the Replit access gate, not Illuminate. Confirm that judges receive the password before rehearsal.
- The first broad API test command used the shared Python interpreter, where pytest was unavailable. Running the locked subproject with `uv run --project /home/runner/workspace/api --extra dev` resolved that harness issue.
- Two program-focus tests require live Neo4j configuration and failed when run before the disposable database was available; the remaining selected tests passed. This is consistent with their live-database dependency, not an assertion failure in mission logic.
- A Vite dependency-optimization reload produced transient development-only Vue warnings on the first Entity Report and Settings captures. Reused-profile route checks passed after optimization.

## Automated checks

| Command/check | Result |
| --- | --- |
| `cd web && npm test` | 7 passed |
| `cd web && npm run build` | Passed; 518 modules transformed |
| Focused catalog/export/SPA API tests | 36 passed |
| Readiness/risk/report/program/claim selection before disposable DB | 71 passed, 2 failed for missing Neo4j password, 3 skipped |
| Disposable offline seed | Passed; 766 nodes and 1,610 relationships across listed labels/types |
| Sequential live mission API probe | All 12 steps passed |
| Configured workflow after credential repair | Running; complete adjacent mission probe passed |
| Reused Chromium route probe | Mission, illumination, vendor risk, comparison, claims, artifacts, and settings rendered |
| Reused-profile interruption/recovery | Unavailable state passed; recovered state passed |

## Retest and regression status

- No code fix merged into this task branch during the initial test window.
- The environment credential repair was retested immediately: the configured workflow started, and mission, graph, preset, report, claims, artifacts, CSV export, catalog dry run, and no-write catalog status all passed.
- The complete live sequence was exercised after the initial configured-workflow failure using isolated data.
- Adjacent checks covered direct history routes, frozen operation during API outage, API restart recovery, export formatting, catalog no-write behavior, and frontend build/unit tests.
- Before completion, shared entry points and the branch tip must be rechecked because parallel tasks are merging concurrently.

## Exit assessment

- Critical defects: 0
- High defects: 1 reported, closed on retest (`E2E-001`)
- Medium defects: 0
- Low defects: 1 reported, open (`E2E-002`)
- Live NDIA writes: 0

No critical or high-severity journey defect observed during this QA remains unreported.