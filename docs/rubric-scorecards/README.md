# Versioned NDIA rubric scorecards

This directory is the audit trail for hostile rubric reviews. A scorecard is
immutable evidence about one evaluated revision and runtime state; do not edit an
old score upward after a fix. Add a new scorecard after the remediation is
merged, refresh the evaluated revision, rerun both targeted checks and the whole
review, and compare the result with the prior pass.

## Frozen judging contract

The authenticated September 8, 2026 event record preserved by the project
publishes six criteria. The raw weights total **101 points** and must not be
normalized:

| Criterion | Raw points | Full-credit standard used by this review |
|---|---:|---|
| Mission Impact | 30 | The running product visibly answers the UC-7 supply-chain and UC-11 vendor-risk missions with actionable, evidence-bounded decision support. |
| Technical Innovation | 25 | Original graph, claim/lineage, deterministic analytics, bounded AI/tooling, and export concepts are both technically credible and inspectable in the evaluated product. |
| Usability & Design | 20 | A clean-session judge can understand and complete the mission journey; loading, error, keyboard, responsive, zoom, theme, and presentation states remain usable. |
| Security & Sustainability | 15 | The evaluated runtime demonstrates bounded operations, protected credentials and writes, explicit failure, maintainable delivery, and truthful production limitations. |
| Team Collaboration | 10 | Repository and presentation evidence demonstrate coordinated ownership, clear handoffs, review discipline, and resilience under pressure. |
| Interoperability | 1 | The product consumes applicable shared datasets and exposes or contributes a safe, documented, machine-readable result for another team. |

The event record does not publish finer point subdivisions in this repository.
Scorecards therefore evaluate each published criterion directly instead of
inventing unofficial subcriteria.

## Award and deduction rules

1. Award credit only for behavior or evidence visible on the exact evaluated
   revision. A task, branch, draft, or merge queue is not evidence of a fix.
2. A document may support a claim only when the running behavior or an executable
   check corroborates claims that are supposed to be implemented.
3. Missing human, organizer, production, source-license, or deployment evidence
   remains blocked. Do not infer it from a local test.
4. A deduction must cite reproducible evidence and an existing owner task or a
   newly proposed, non-overlapping task. External confirmations may use the task
   that records that confirmation.
5. A clean pass starts with a new browser profile, uses the browser origin,
   follows the rendered mission action, and requires loaded findings and vendor
   assessments rather than static page chrome.
6. A final **101/101** requires all criteria to have current evidence and two
   consecutive complete passes on the same revision. Technical rehearsal passes
   alone do not satisfy that convergence rule.

## Runtime preconditions

- Record the commit, branch/ref relationship, date, runtime type, deployment
  state, fixture/live state, optional-service state, and any inability to prove
  that the revision is current main.
- Start the configured workflow and require `/api/health?refresh=true` to report
  database health and primary-workflow readiness.
- Run two clean-profile judge journeys, the negative rehearsal-harness test, the
  complete backend suite, the web production build, focused optional-dependency
  failure tests, and mission performance budgets.
- Inspect the visible desktop result and the browser/runtime logs. Run the
  responsive, keyboard, zoom, theme, and accessible-name matrix when the browser
  gate supports it; otherwise deduct rather than assuming.
- Inspect the live export/schema response and distinguish catalog dry-run or
  configuration from a successful organizer receipt.

## Scorecard index

| Version | Evaluated revision | Result | Stop reason |
|---|---|---:|---|
| [v1](v1-e4473a1.md) | `e4473a1f446b83ebea92d79c7b8db959cf42cbe5` | **78.7/101** | Explicit blockers; not a perfect pass |
| [v2](v2-933c998.md) | `933c998a7aacac9570d8de242e43915d38e93074` | **78.7/101** | Repaired regression pass; original evidence blockers remain |
| [v3](v3-0d30bd6.md) | `0d30bd6b3e63ab9a3875a5dadbfa9a7f1bd3556e` | **78.7/101** | Pre-navigation assembled pass; original evidence blockers remain |
| [v4](v4-8e0d93b.md) | `8e0d93b9610c5542c976c5fc14faf7de788527e3` | **78.7/101** | Current post-navigation assembled pass; original evidence blockers remain |