# Supply Chain Journey Review

**Review date:** 2026-09-08  
**Build:** `4fa0a1f`  
**Environment:** Replit development workflow `UC7 Illuminate`  
**Program:** V-22 Osprey Program (PMA-275), `ent_6484d4d13b76`  
**Data state:** deterministic `uc7-fixtures-v1`; offline seed with the simulated scenario enabled  
**Operational state:** primary database workflow ready; operational live refresh not ready; source coverage empty; freshness unknown  

## Persona and decision boundary

This review adopted the supply-chain or logistics analyst in
`docs/NDIA_USER_PERSONAS.md`. The analyst needed to trace multi-tier
dependencies, sole-source or concentration exposure, hidden ownership/control
paths, geography, and supporting evidence, then state a bounded readiness
implication and a concrete collection question.

The review did not infer complete supplier tiers, capacity, lead time,
component substitution, or alternate sources. A visible edge was not treated as
an approved fact without its truth and simulation state, and simulated
relationships were not treated as observed allegations.

## Evaluated build and data

The workflow initially failed before the UI loaded because the root runtime
environment did not contain `asyncpg`, although it is declared in the API
subproject lockfile. Installing that already-declared dependency restored the
workflow without a product change. This recovery risk is already covered by
Task #43 (Catch dependency recovery regressions before they reach a demo), so no
duplicate was created.

After startup, `/api/health` reported:

- `primary_workflow_ready: true`;
- `operational_live_ready: false`;
- 1,848 nodes and 1,809 relationships;
- validated seed coverage of 32 primes and 26 subcontractors;
- no source-coverage rows; and
- freshness `unknown`, with no latest retrieval timestamp.

The evaluated state is therefore a useful frozen rehearsal graph, not current
operational intelligence.

## Completed reviewer scenario

### 1. Begin at the V-22 program

The mission entry selected V-22, presented a clear simulation boundary, and
offered direct supply-exposure, hidden-control, sole-source, and portfolio
actions. Program scope survived transitions into Explorer, Portfolio, and
vendor detail.

The page also paired `Mission ready` with no source coverage, unknown
freshness, and operational live readiness false. Task #129 (Make rehearsal data
unmistakable before acquisition decisions) already covers that data-mode
distinction.

### 2. Trace supplier tiers and geographic exposure

The guided manufacturing lens for country `CN`, minimum tier 2 returned one
match:

- Ningbo Precision Castings Ltd (simulated), tier 3;
- typed supply path through AVIAN, LLC and AVIAN-PRECISE COMPANY, LLC to V-22;
- manufacturing location `CN`; and
- a conspicuous simulated-data label in the global header, result summary, and
  vendor detail.

The canvas preserved the whole 59-vendor mission graph. That provided context,
but the result-first path was difficult to isolate from the dense graph until
the analyst opened the Path list.

### 3. Locate sole-source and concentration exposure

The sole-source template returned 12 rows across 11 unique suppliers. It named
BELL BOEING JOINT PROJECT OFFICE first and included tier and, where available,
PSC and contract references. The broader program supply-chain contract also
contained:

- 12 sole-source findings;
- six category-concentration findings;
- one tier-1 exposure-concentration finding reporting BELL BOEING at 93% of
  observed tier-1 supplier exposure; and
- explicit intelligence-gap findings for component criticality, capacity, lead
  time, alternate count, and category.

The graph summary communicated supplier name and simulation status, but did not
show the finding contract's severity, confidence, freshness, source count,
award context, or unknowns beside the path.

### 4. Follow hidden ownership/control paths

The foreign-parent lens returned seven path rows representing four unique
suppliers: SUBARU CORPORATION, CANADIAN COMMERCIAL CORPORATION, QUEST GLOBAL
SERVICES-NA, INC., and the simulated Ningbo supplier. The result retained typed
control and geography edges and clearly marked paths involving simulated data.

Multiple graph paths to the simulated supplier produced duplicate result rows.
That is explainable graph multiplicity, but the guided summary did not say
whether repeated rows were distinct control routes or duplicate affected
vendors.

### 5. Verify identity and supporting evidence

Opening BELL BOEING's V-22-scoped report exposed UEI, source, method,
confidence, retrieval date, category, tier, sole-source flag, PSC, NAICS,
contract reference, amount, and the supplying edge. The simulated Ningbo report
made the allegation boundary especially clear and excluded simulated evidence
from its normal risk-category completeness.

At the guided graph boundary, however, the Path list reduced nodes to
`live/curated` versus `simulated` and relationships to type plus an optional
source URL. It did not expose current claim status, identifier match method,
source count, freshness, affected award, or a complete claim-to-artifact route.
Task #134 records this validated gap.

### 6. Determine truth, simulation, and intelligence gaps

The captured `findings` array in
`docs/reviews/supply-chain-journey/program-supply-chain.json` contained 335
records:

- 274 explicit intelligence gaps;
- 323 non-simulated and 12 simulated findings;
- 221 with an affected award and 114 without one; and
- all 335 records with `freshness: "unknown"`.

Unknowns were not computed as safe conditions in the backend contract. The
vendor report also used `MISSING`, `No data`, and `complete diligence` rather
than a reassuring clear result. The remaining problem is presentation: those
unknowns and freshness values are not adjacent to the guided path where the
analyst forms the readiness implication.

## Edge-state and recovery review

| State | Result | Analyst interpretation |
| --- | --- | --- |
| Dense graph | **Partial** | Full mission context remained available, but the matching path competed with dozens of suppliers and location/category edges. |
| Empty template result | **Fail** | A valid no-match query (`country=ZZ`) was labeled `Guided analysis could not finish` and `no usable graph results`, conflating zero matches with execution failure. |
| Partial source state | **Partial** | Entry and Portfolio warned about unavailable/loading reports, but the guided path did not carry source coverage or completeness. |
| Stale/unknown freshness | **Fail at path** | All findings reported unknown freshness in the contract, but no freshness warning appeared beside the guided result. |
| Simulated path | **Pass** | Simulation was visually contagious across the global header, graph summary, highlighted nodes, and vendor report. |
| Failed dependency | **Recovered** | The stopped workflow gave an actionable startup failure; Task #43 already covers automated recovery regression checks. |
| Portfolio filtering | **Pass with scope-label issue** | Tier, category, risk, confidence, completeness, freshness, and observed/simulated filters worked; the initial loading copy used the raw program ID before the human-readable label was available. |
| Vendor transition | **Pass** | Mission context survived into vendor detail, and simulated evidence was excluded from normal risk-category coverage. |

Task #135 records the validated empty, partial, dense, and mission-label
recovery issues.

## Required readiness implication and collection question

V-22 has recorded sole-source and concentrated tier-1 dependencies, while the
simulated scenario demonstrates how a tier-3 casting supplier with China
manufacturing and foreign control could create an upstream readiness concern;
this supports prioritizing review, not a conclusion about current capacity or
disruption. Before contingency action, collect current approved evidence for
alternate suppliers, capacity, lead time, and component criticality for each
affected award, and verify every material supply/control edge through its
current claim and source artifact.

## Comprehension results

- **Is every visible relationship an approved real-world fact?** No. The
  reviewed graph includes curated and simulated paths, and the analyst still
  needs claim-level status for each material edge.
- **Does high match confidence imply complete supplier coverage?** No. The
  contract contained hundreds of explicit intelligence gaps and no current
  freshness evidence.
- **Does missing alternate-source data prove sole source?** No. An explicit
  sole-source relationship is different from an unknown alternate count.
- **May capacity or lead time be estimated from the risk score?** No. Both are
  explicit intelligence gaps in this reviewed state.
- **Can the result support contingency analysis today?** It can prioritize
  evidence collection and supplier review, but it cannot support a capacity,
  lead-time, substitution, or complete-tier assertion.

## Follow-on coverage

Existing work reused rather than duplicated:

- Task #43 — Catch dependency recovery regressions before they reach a demo
- Task #50 — Gate The Judge Journey
- Task #69 — Turn approved climate and logistics sources into live evidence
- Task #71 — Use each source’s own freshness window before calling data stale
- Task #84 — Keep decision evidence reachable when requests fail
- Task #85 — Stop calling approved evidence automatically verified
- Task #86 — Prevent unsupported clear results and recommendations
- Task #100 — Back every sole-source risk score with reviewable evidence
- Task #129 — Make rehearsal data unmistakable before acquisition decisions

New follow-ons from this review:

- Task #134 — Put evidence status beside every supply-chain path
- Task #135 — Explain empty, partial, and crowded supply-chain results

### Follow-on audit matrix

| Task | Priority and user impact | Reproduction evidence | Acceptance boundary | Starting files |
| --- | --- | --- | --- | --- |
| #134 | **High.** Analysts cannot defend a readiness implication when freshness, source count, award, claim status, and intelligence gaps are detached from a successful guided path. | Run the three V-22 presets, open Path list, and compare the visible rows with `program-supply-chain.json`; see `supply-exposure.jpg`, `sole-source.jpg`, and `hidden-control.jpg`. | Present the existing finding and relationship evidence beside the typed path; label missing values unknown. Do not add datasets, alter scoring/truth rules, or weaken simulation boundaries. | `web/src/views/Explorer.vue`, `web/src/components/GraphFindingList.vue`, `web/src/components/EdgeInspector.vue`, `web/src/components/Inspector.vue`, `web/src/api/client.ts`, `api/illuminate/supply_chain.py`, `api/illuminate/routers/graph.py` |
| #135 | **High.** Analysts may abandon valid work or mistake absence for safety when zero matches, incomplete truth, failures, and truncation share generic states. | Run V-22 Supply exposure; then use `country=ZZ`, observe the failure-styled no-match state, review raw-ID portfolio loading, and compare `health.json`; see `empty-supply-exposure.jpg`, `supply-exposure.jpg`, and `portfolio.jpg`. | Start with a compact matching path and distinguish zero match, no eligible evidence, partial/stale data, hidden layers, request failure, and truncation. Do not change graph analytics, scoring, or add datasets. | `web/src/views/Explorer.vue`, `web/src/views/Portfolio.vue`, `web/src/components/GraphCanvas.vue`, `web/src/components/GraphFindingList.vue`, `web/src/stores/graph.ts`, `api/illuminate/supply_chain.py`, `api/illuminate/routers/query.py` |

Task #134 is distinct from Task #84, which preserves decision evidence when a
request fails, and Task #85, which owns the shared truth-status vocabulary:
#134 presents already-returned fields beside successful guided graph paths.
Task #135 is distinct from Task #86, which aligns risk-report narrative and
recommendation rules: #135 covers interaction and recovery semantics for graph
and portfolio result states. Task #50 remains the broader automated journey
gate; it should exercise these behaviors after implementation rather than own
their product changes.

## Evidence

- `docs/reviews/supply-chain-journey/health.json`
- `docs/reviews/supply-chain-journey/manufactures_in.json`
- `docs/reviews/supply-chain-journey/sole_source.json`
- `docs/reviews/supply-chain-journey/foreign_parent.json`
- `docs/reviews/supply-chain-journey/program-supply-chain.json`
- `docs/reviews/supply-chain-journey/vendor-report.json`
- `docs/reviews/supply-chain-journey/mission-entry.jpg`
- `docs/reviews/supply-chain-journey/supply-exposure.jpg`
- `docs/reviews/supply-chain-journey/sole-source.jpg`
- `docs/reviews/supply-chain-journey/hidden-control.jpg`
- `docs/reviews/supply-chain-journey/portfolio.jpg`
- `docs/reviews/supply-chain-journey/filtered-portfolio.jpg`
- `docs/reviews/supply-chain-journey/simulated-vendor-detail.jpg`
- `docs/reviews/supply-chain-journey/empty-supply-exposure.jpg`