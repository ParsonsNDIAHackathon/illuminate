# Illuminate End-to-End UX Review

Reviewed: September 8, 2026

## Executive assessment

**Release recommendation: conditional fail for an unguided non-expert journey.**

Illuminate has a credible decision-support structure: the mission page frames the
question, separates readiness from optional services, exposes source coverage,
offers deterministic actions, and repeats the simulation boundary. Portfolio,
comparison, and vendor reports separate risk from evidence quality more clearly
than the earlier screen captures, and the program-management page has unusually
complete loading, empty, error, validation, and recovery states.

The assembled journey is not yet unambiguous enough to claim that a new user can
complete mission → illuminate → assess → compare → inspect evidence → export
without assistance. The highest-impact breaks are:

1. A guided graph action ends on a dense graph without a concise finding result
   or reliable retry of the failed analysis.
2. Mission context is not consistently preserved into triage and comparison;
   report-to-comparison can show an unrelated frozen preset.
3. Claim approval, evidence verification, derivation, freshness, and simulation
   are not modeled consistently in labels across surfaces.
4. Report, claims, artifacts, connectors, and secondary indexes can fail without
   an explicit error/retry state.
5. The graph has no equivalent non-pointer investigation path, and several
   routed/icon interactions lack complete keyboard and focus semantics.
6. Export is presented as a direct default-page CSV download even though the
   underlying interoperability contract is paginated and substantially richer.

No fixes were made during this review.

## Review evidence and limits

The assessment used:

- the five shared NDIA roles defined for the product;
- the primary UC-7 and UC-11 mission contract;
- static review of all routed frontend surfaces and relevant report/export
  contracts;
- the committed 1500 × 900 desktop screen-capture set in `docs/screenshots/`;
- current 1280 × 720 live route captures in `review-screenshots/` for Mission,
  Graph, Portfolio, Comparison, Vendor Report, Claims, Artifacts, and Connectors;
- the deterministic request-performance baseline in
  `docs/mission-performance-budgets.md`;
- three independent source-review passes conducted for this report, focused on
  journey, truth-state comprehension, and accessibility/responsive presentation;
- current project-task plans, used to deduplicate ownership.

The initial live pass was blocked because the existing Neo4j data required its
protected local password. The review did not reset the graph or bypass that
protection. After the credential became available through the protected
environment, the configured workflow started normally (Neo4j ready in 26
seconds, API ready in 36 seconds, and Vite serving on port 8080). Static live
captures were then taken for the eight routes listed above. Consequently:

- source-level findings are validated;
- the principal desktop hierarchy, density, terminology, and visible-state
  observations are validated against the current running application;
- the vendor-report capture emitted an unhandled Vue mounted-hook error while
  visible report data remained on screen, reinforcing the need for explicit
  partial/failure state handling in UX-07;
- mobile, keyboard, screen-reader, contrast, fault-injection, and human elapsed
  times are **not runtime passes**;
- those runtime checks remain assigned to Task #29 (QA End To End Mission),
  Task #50 (Gate The Judge Journey), and Task #21 (Rehearse Rubric Ready Demo).

## Review matrix

| Persona | Primary question | Journey exercised | Comprehension checks | Success signal |
| --- | --- | --- | --- | --- |
| Acquisition/program decision-maker | Which dependency threatens readiness, why is it credible, and what should we do next? | Mission → guided finding → vendor assessment → compare → evidence → export | Risk vs evidence quality; readiness effect; recommendation is advisory; simulation is not allegation | First actionable finding under 60 seconds; comparison under 3 minutes |
| Supply-chain/logistics analyst | Where are the deep-tier, sole-source, concentration, ownership, geographic, or alternate-source exposures? | Program → graph path → edge/report context → evidence → triage | Unknown is not clear; path and affected program/award are visible; criticality and alternate-source gaps are explicit | Can explain the path and next investigation without decoding raw graph internals |
| Counterintelligence/vendor-risk analyst | Which indicators merit scrutiny, what supports them, and what human decision is defensible? | Triage → comparison → report factors → claim/artifact → decision | Score, band, confidence, completeness, freshness, claim state, derivation, and simulation remain separate | Every material factor reaches a specific claim/artifact/source and rule |
| Integration partner | Can another team consume a complete, bounded, versioned finding safely? | Export discovery → preview/schema → full or incremental retrieval | Pagination, watermark, classification, provenance, lifecycle, simulation, and limitations are explicit | Can integrate without undocumented UI knowledge or silently dropping records |
| Deployment/data operator | Is the deterministic mission ready, what is optional, and how do I recover safely? | Readiness → connectors → jobs/settings → publication state | Configured is not tested; optional failures do not masquerade as primary failure; dry-run differs from published | Can diagnose and recover without exposing secrets or changing evidence accidentally |

### Shared expectations

- Decision support must never read as adjudication, award eligibility, or an
  allegation.
- Missing evidence must lower completeness/confidence or create diligence work;
  it must not lower risk or imply a clear result.
- Review lifecycle, derivation, freshness, and simulation are separate
  dimensions even when shown together.
- Executive clarity and analyst depth should be reconciled through progressive
  disclosure, not by removing provenance or operator diagnostics.
- The deterministic judged path must remain complete when optional models,
  connectors, and catalog writes are unavailable.

## Timed checkpoints

### First actionable finding — target under 60 seconds

**Status: at risk; not demonstrated with a human timer.**

The mission page makes the first guided action one click away, and the measured
warm backend operations are well within the five-second system budget (graph
maximum 37 ms and named preset maximum 44 ms in the recorded baseline). The
human checkpoint still fails structurally because the action lands on the graph
without selecting or summarizing the result. A new user must interpret a dense
canvas, choose a node or edge, and discover the report/evidence path. If the
preset fails, the visible retry reloads graph context rather than rerunning the
failed analysis.

The timed pass must end only when the participant can state:

- the affected program/vendor;
- the risk or gap;
- whether the data is observed, derived, reviewed, or simulated;
- the next useful action.

### Trustworthy-versus-risky comparison — target under three minutes

**Status: preset path is structurally short; general path does not pass.**

The mission page offers a direct frozen comparison and the two-column comparison
is responsive in source. The normal report path passes only a left-side ID.
Unless both internal IDs are already present, the comparison loads an unrelated
frozen pair, while the live form asks the user to type entity IDs. Triage also
drops mission scope and the “trustworthy” sort ranks evidence quality before
risk, so a well-evidenced risky vendor can be presented first.

The timed pass must require a participant to select both vendors intentionally,
explain the same scoring framework on both sides, identify at least one
evidence-quality difference, and reach a specific evidence record.

## Journey and route assessment

| Surface | What works | Principal issue | Verdict |
| --- | --- | --- | --- |
| Mission | Clear mission question, readiness, coverage, deterministic actions, workflow outline, and simulation boundary | “P/S,” source-record counts, and operator terms need explanation; guidance says to add a program in Settings although Programs owns that action | Strong entry, but downstream context must be preserved |
| Graph | Program scope, search, report trace, simulation styling, truncation notice, inspector, and query depth are available | Too many simultaneous controls/panes; preset results lack a decision summary; retry can target the wrong operation; canvas is pointer-dependent | High-risk break in first-finding journey |
| Portfolio | Explicitly separates risk from confidence, completeness, and freshness; handles loading, no data, filters, partial reports, and stale evidence | Nine control groups and eleven columns dominate; mission scope is lost; “trustworthy” semantics are unsafe; partial rows cannot be retried | Powerful analyst view, weak first-use triage |
| Comparison | Same categories, weights, gaps, contribution, freshness, confidence, and simulation labels on both sides | Live selection requires internal IDs; a left-only report link loads unrelated frozen profiles; factor evidence is not directly actionable | Useful judged preset, broken contextual comparison |
| Vendor report | Strong category/factor/provenance detail, diligence gaps, graph traces, claim/artifact links, and local simulation warnings | Initial failures spin indefinitely; narrative “clear” indicators can disagree with the scoring eligibility rules; evidence links are often entity-wide rather than factor-specific | Strong investigation depth with truth/recovery defects |
| Claims | Staged, committed, rejected tabs; source, method, confidence, evidence, retrieval time, and simulation are shown | Committed is relabeled VERIFIED; disputed is absent; mutation rationale/status/error feedback are incomplete | Review state is visible but semantically unsafe |
| Artifacts | Source, about-entity, retrieval time, attached claims, safe viewer, and simulation are shown | One committed linked claim makes the whole artifact “verified,” hiding mixed outcomes; list retrieval has no failure/retry state | Evidence inventory is useful, aggregate status misleads |
| Connectors | Credential boundary, trust class, individual tests, and sanitized test failures are present | Green connected state means credential configured, not successful verification; save/replace/remove do not invalidate or run diagnostics; load/mutations lack recovery | Operator readiness can be overstated |
| Programs | Clear browse/add workflow with validation, skeleton, empty state, error, retry, success, and stale-response protection | Program-to-mission/graph context is not explained | Best state handling in the product |
| Entities and People | Searchable inventories and report links expose useful identifiers, roles, parents, sources, and interlocks | Wide technical tables, unexplained graph terms, no explicit load failure/retry, and mouse-oriented whole-row navigation in Entities | Appropriate secondary depth, not a primary journey |
| Settings/catalog | Confirmation, permission, dry-run, publication gating, refresh, and responsive form rules are present | Event IDs, operator authorization, MCP, and raw errors assume specialist knowledge | Operator-only surface; keep behind clear navigation |
| Export | Backend offers schema, fields, sample, pagination, incremental watermarks, JSON/NDJSON/CSV, lineage, rejection, and simulation rules | Global Export silently downloads only the default 100-record page, with continuation in headers and no scope/count/status/recovery UI | UI materially understates and can truncate the product |

## Comprehension and truth-state consistency

| Concept | Current clarity | Finding |
| --- | --- | --- |
| Risk score/band | Generally distinct in portfolio, comparison, and report | Good foundation, but report narrative indicators use looser “clear” rules than the scoring contract |
| Confidence | Visible separately in portfolio, comparison, report factors, claims | Meaning is not defined in-product and does not constrain every recommendation |
| Completeness | Visible separately and gaps are explicit | Stale evidence still counts as complete category coverage; copy must explain that completeness is coverage, not investigation completion |
| Freshness | Current/stale/missing/diligence labels are visible | Stale/unknown evidence creates a flag but can still leave a standard-monitoring disposition |
| Recommendation/disposition | Present on standardized profiles | Values are rendered from machine labels and can imply readiness despite stale evidence; human decision remains separate work |
| Provenance | Source, retrieval, method, confidence, rule, claim, and artifact data are often available | Comparison factors and report categories do not consistently link to the exact claim/artifact/source |
| Verified/committed | `TruthBadge` turns committed into VERIFIED | Approval lifecycle is conflated with verification/source authority |
| Derived | Shown on risk factors | Graph rendering does not expose review/freshness dimension with derivation |
| Staged/rejected | Visible in Claims and aggregate Artifacts | Artifact-level reduction hides mixed claim outcomes |
| Disputed | Supported as a required product state | Not exposed consistently in claims, badges, or export normalization |
| Simulated | Repeated globally and locally; graph uses text, line style, and border style, not color alone | Strongest safety treatment; preserve it through all simplification work |

### Truth-safety defects validated in source

1. The standardized risk contract only treats explicit boolean sole-source facts
   as evidence, while the narrative report calls any supply set without a truthy
   sole-source flag “No sole-source awards on record.”
2. A public ticker with available filings is narrated as clear financial health
   even when no financial screen exists.
3. Stale evidence contributes to category coverage; freshness creates diligence
   flags, but the disposition rule does not itself require fresh/current
   evidence.
4. Every committed claim is displayed as VERIFIED, including claims
   auto-committed from configured source policy.
5. An artifact is displayed as verified when any attached claim is committed,
   even if other linked claims are staged or rejected.
6. Export normalizes any state outside staged/committed/rejected to unknown, so
   disputed state is not preserved as a first-class lifecycle value.

## State and recovery assessment

| State | Strong examples | Gaps |
| --- | --- | --- |
| Loading | Mission readiness, Programs skeleton, Portfolio staged identity/report loading, graph spinner | Vendor report gives only an indefinite bar; Claims, Artifacts, Connectors, Entities, and People do not announce context |
| Empty | Programs distinguishes search-empty from first-program; Portfolio distinguishes no portfolio from no filter match | Claims, Artifacts, Entities, People, and Connectors can look empty after failure |
| Partial | Portfolio retains identity rows and warns about failed contracts; graph warns when a report trace references unavailable elements | Portfolio has no row/partial retry; report evidence sections do not consistently state partial contract failure |
| Stale | Mission and Portfolio display freshness advisories; report factors show freshness badges | Recommendation semantics do not consistently require remediation before action |
| Failure | Mission, Programs, Portfolio index, graph, comparison, and artifact viewer show some explicit failures | Report load, list routes, claim decisions, connector load/save/remove, and direct export lack complete failure feedback |
| Recovery | Mission, Programs, Portfolio index, graph reload, comparison frozen fallback, Settings refresh | Graph retry does not rerun the failed preset; partial reports and most secondary lists cannot be retried in place |

## Interaction, accessibility, and presentation

### Information architecture and progressive disclosure

- The global rail exposes eleven equal-weight destinations plus settings-related
  duplication. A new user must infer the relationship among Mission, Graph,
  Triage, Compare, Claims, Artifacts, and Export.
- Mission successfully uses plain questions as the primary entry. Graph,
  portfolio, and settings then expose specialist controls without enough
  progressive disclosure.
- The report tab model is understandable and keeps analyst depth behind a vendor
  context. Specific evidence should remain one action away from each factor.

### Keyboard and focus

- The Cytoscape canvas is the only way to select and expand graph nodes/edges;
  no keyboard-equivalent finding/path list is available.
- Entities uses whole-row click navigation without a visible keyboard link in
  the row.
- Several icon-only controls rely on an icon or `title` rather than a complete
  accessible name, including report back navigation, connector credential
  removal, and artifact-viewer close.
- Routed transitions do not move focus to the new page heading or otherwise
  announce page context. Dialog/route focus restoration requires runtime
  verification.

### Projector readability and visual hierarchy

- Mission has the clearest hierarchy and large type.
- Both the current 1280 × 720 and committed 1500 × 900 graph captures show
  dozens of labels, simultaneous controls, inspector, and chat competing for
  attention. Important node and edge labels are 9–10 px in source and are not
  presentation-safe by default.
- Portfolio retains 8–10 px metadata and a minimum 1160 px table. Claims,
  Artifacts, Entities, and People use minimum widths from 930 to 1380 px.
- Theme behavior requires the same browser validation as contrast and responsive
  layout; no theme variant received a runtime pass in this review.

### Responsive behavior

- The shell changes to a temporary drawer, hides the avatar/context chip at
  narrow widths, and the mission and comparison grids collapse.
- Graph reflows into vertically stacked canvas/side regions, but the resulting
  minimum-height stack is long and still depends on a pointer-oriented canvas.
- Wide tables use local overflow rather than forcing deliberate document
  overflow. They remain difficult to scan on a phone and need persistent row
  context and keyboard-scroll verification.
- The current capture pass proves only the 1280 × 720 desktop surface. It does
  not prove the required 320, 375, 414, 720/768, 1024, and 1440 widths, 200%
  zoom, measured contrast in both themes, or unobscured focus. These are
  explicit acceptance checks in Task #50.

### Interaction consistency

- Retry labels do not always repeat the failed operation.
- Program selection, graph focus, portfolio scope, report context, and compare
  selection are not one consistent state model.
- Some evidence links open exact sources, while others open an entity-wide
  claims/artifacts collection.
- Loading and mutation feedback varies from full state panels to silent
  asynchronous calls.

## Prioritized findings and ownership

Existing simplification, QA, interoperability, operator, and persona tasks own
the findings that fall within their accepted scope. Three additional,
non-duplicate implementation tasks were created for gaps that those tasks only
validate:

- [**Task #84 — Keep decision evidence reachable when requests fail**](../.local/tasks/decision-evidence-recovery.md)
- [**Task #85 — Stop calling approved evidence automatically verified**](../.local/tasks/approval-verification-labels.md)
- [**Task #86 — Prevent unsupported clear results and recommendations**](../.local/tasks/risk-narrative-evidence-rules.md)

The mappings below are the deduplicated defect register for this review.

### UX-01 — Guided graph actions do not end in an actionable finding

- **Severity:** High
- **Personas:** Acquisition/program decision-maker; supply-chain/logistics analyst
- **Evidence:** `web/src/views/Explorer.vue`; `web/src/components/GraphCanvas.vue`;
  `web/src/stores/graph.ts`
- **Acceptance:** Each preset ends with a focused finding summary naming affected
  program/vendor, path, risk/gap, truth/simulation status, and next action.
  Failure retry reruns the preset with preserved parameters.
- **Scope boundary:** Do not change analytics or query semantics.
- **Primary owner:** [Task #60 (Simplify Graph Workspace)](../.local/tasks/simplify-graph-workspace.md).
- **Validated by:** Task #50 (Gate The Judge Journey) and Task #21 (Rehearse
  Rubric Ready Demo).

### UX-02 — Mission, report, triage, and comparison lose user context

- **Severity:** High
- **Personas:** Acquisition/program decision-maker; vendor-risk analyst
- **Evidence:** `web/src/views/MissionEntry.vue`; `web/src/views/Portfolio.vue`;
  `web/src/views/EntityReport.vue`; `web/src/views/VendorComparison.vue`;
  `web/src/router.ts`
- **Acceptance:** Program scope persists through triage/report/graph; Compare
  preserves the selected left vendor, provides a searchable right-vendor
  selection, and never substitutes an unrelated preset without explicit choice.
- **Scope boundary:** Preserve route compatibility and frozen offline preset.
- **Primary owner:** [Task #59 (Simplify Product Navigation)](../.local/tasks/simplify-product-navigation.md);
  mission-scoped triage is owned by
  [Task #61 (Simplify Portfolio Triage)](../.local/tasks/simplify-portfolio-triage.md).
- **Validated by:** Task #75 (Evaluate Acquisition Decision Journey).

### UX-03 — Portfolio defaults overload users and can misstate “trustworthy”

- **Severity:** High
- **Personas:** Acquisition/program decision-maker; vendor-risk analyst;
  supply-chain/logistics analyst
- **Evidence:** `web/src/views/Portfolio.vue`
- **Acceptance:** Default scope is mission-relevant, initial ranking is
  defensible without configuration, “trustworthy” cannot rank a high-risk vendor
  solely because evidence is complete, report loading is bounded, and failed
  rows can retry without losing filters or successful rows.
- **Scope boundary:** Do not recalibrate the underlying score contract.
- **Primary owner:** [Task #61 (Simplify Portfolio Triage)](../.local/tasks/simplify-portfolio-triage.md);
  cross-surface recovery is owned by
  [Task #84](../.local/tasks/decision-evidence-recovery.md).
- **Validated by:** Task #50 (Gate The Judge Journey) and Tasks #75–77 (persona
  journeys).

### UX-04 — Exact evidence is not consistently one action from a factor

- **Severity:** High
- **Personas:** Vendor-risk analyst; acquisition/program decision-maker;
  integration partner
- **Evidence:** `web/src/components/VendorRiskColumn.vue`;
  `web/src/views/EntityReport.vue`; `web/src/views/Claims.vue`;
  `web/src/views/Artifacts.vue`
- **Acceptance:** Every material and clear factor can open the exact claim,
  artifact/source, retrieval context, and rule; unavailable destinations say
  why. Entity-wide evidence pages retain the originating factor context.
- **Scope boundary:** Use the existing provenance model; do not redesign backend
  contracts without a demonstrated missing field.
- **Primary owner:** [Task #84 (Keep decision evidence reachable when requests
  fail)](../.local/tasks/decision-evidence-recovery.md).
- **Validated by / related:** Task #77 (Evaluate Vendor Risk Journey), Task #50
  (Gate The Judge Journey), and Task #63 (Record Analyst Decisions).

### UX-05 — Approval, verification, derivation, and dispute are conflated

- **Severity:** High
- **Personas:** Vendor-risk analyst; integration partner; operator/auditor
- **Evidence:** `web/src/components/TruthBadge.vue`; `web/src/views/Claims.vue`;
  `web/src/views/Artifacts.vue`; `api/illuminate/routers/exports.py`
- **Acceptance:** Approval lifecycle, source authority/verification, derivation,
  freshness, and simulation remain separate; mixed artifact outcomes are shown;
  disputed state survives claims, reports, artifacts, and export.
- **Scope boundary:** Do not weaken simulation labels or approval gates.
- **Primary owner:** [Task #85 (Stop calling approved evidence automatically
  verified)](../.local/tasks/approval-verification-labels.md).
- **Validated by / related:** Task #63 (Record Analyst Decisions), Task #66
  (Keep materialized ownership edges aligned with claim decisions), Task #77
  (Evaluate Vendor Risk Journey), and Task #50 (Gate The Judge Journey).

### UX-06 — Narrative “clear” results and dispositions can outrun evidence

- **Severity:** High
- **Personas:** Acquisition/program decision-maker; vendor-risk analyst;
  supply-chain/logistics analyst
- **Evidence:** `api/illuminate/report.py`; `web/src/views/EntityReport.vue`;
  `web/src/components/VendorRiskColumn.vue`
- **Acceptance:** Unknown sole-source values and filing availability without a
  financial assessment render as not assessed, not clear. Narrative and
  standardized categories use the same evidence-eligibility rules. Stale or
  unknown evidence creates an explicit diligence prerequisite before a normal
  monitoring recommendation.
- **Scope boundary:** Align presentation with the defined deterministic contract;
  do not recalibrate weights from reviewer preference.
- **Primary owner:** [Task #86 (Prevent unsupported clear results and
  recommendations)](../.local/tasks/risk-narrative-evidence-rules.md).
- **Validated by / related:** Tasks #76–77 (Supply Chain and Vendor Risk persona
  reviews), Task #71 (Use each source’s own freshness window before calling data
  stale), and Task #63 (Record Analyst Decisions).

### UX-07 — Failure and recovery behavior is inconsistent

- **Severity:** High
- **Personas:** All human personas
- **Evidence:** `web/src/views/EntityReport.vue`; `web/src/views/Claims.vue`;
  `web/src/views/Artifacts.vue`; `web/src/views/Connectors.vue`;
  `web/src/views/Entities.vue`; `web/src/views/People.vue`;
  `review-screenshots/ux-report.jpg` and its unhandled mounted-hook browser log
- **Acceptance:** Timeout/500 and mutation failures produce announced,
  context-specific errors and retry; never false-empty, indefinite spinner,
  stale previous-entity content, or duplicate action. Successful partial data
  remains available during retry.
- **Scope boundary:** Frontend recovery semantics; backend dependency recovery
  remains separate.
- **Primary owner:** [Task #84 (Keep decision evidence reachable when requests
  fail)](../.local/tasks/decision-evidence-recovery.md).
- **Validated by / related:** Task #29 (QA End To End Mission), Task #50 (Gate
  The Judge Journey), and Task #43 (Catch dependency recovery regressions before
  they reach a demo).

### UX-08 — Keyboard and route-focus access is incomplete

- **Severity:** High
- **Personas:** Keyboard and screen-reader users across all roles
- **Evidence:** `web/src/components/GraphCanvas.vue`; `web/src/views/Entities.vue`;
  `web/src/views/EntityReport.vue`; `web/src/views/Connectors.vue`;
  `web/src/components/ArtifactViewer.vue`; `web/src/App.vue`; `web/src/router.ts`
- **Acceptance:** A non-pointer path can select a finding/path, inspect its
  evidence, and return. Every icon control has a meaningful accessible name.
  Routes and dialogs provide logical, visible focus entry/restoration in both
  themes.
- **Scope boundary:** Keep the graph canvas; add equivalent access rather than
  replacing the visualization framework.
- **Primary owners:** [Task #59 (Simplify Product Navigation)](../.local/tasks/simplify-product-navigation.md)
  for route/dialog focus and
  [Task #60 (Simplify Graph Workspace)](../.local/tasks/simplify-graph-workspace.md)
  for equivalent non-pointer investigation.
- **Validated by:** Task #50 (Gate The Judge Journey).

### UX-09 — Projector, small-screen, zoom, and theme readiness are unproven

- **Severity:** Medium
- **Personas:** Presenter; low-vision users; mobile analysts; all reviewing roles
- **Evidence:** `review-screenshots/ux-graph-preset.jpg`;
  `docs/screenshots/01-explorer.png`;
  `web/src/components/GraphCanvas.vue`; `web/src/views/Portfolio.vue`;
  `web/src/views/Claims.vue`; `web/src/views/Artifacts.vue`;
  `web/src/views/Entities.vue`; `web/src/views/People.vue`
- **Acceptance:** Essential evidence is readable at 1500 × 900 projection;
  required viewport widths and 200% zoom have no document overflow, obscured
  focus, or lost row identity; horizontal regions are keyboard-scrollable; both
  themes maintain readable contrast.
- **Scope boundary:** No broad rebrand or frontend replacement.
- **Owned by:** Task #50 (Gate The Judge Journey), Task #21 (Rehearse Rubric
  Ready Demo), [Task #60](../.local/tasks/simplify-graph-workspace.md), and
  [Task #61](../.local/tasks/simplify-portfolio-triage.md).

### UX-10 — Connector configuration is presented as operational health

- **Severity:** Medium
- **Personas:** Deployment/data operator
- **Evidence:** `web/src/views/Connectors.vue`;
  `api/illuminate/connectors/base.py`
- **Acceptance:** Configured, testing, tested-current, failed, and unconfigured
  are separate states with timestamps. Save runs the safe diagnostic; replace or
  remove invalidates prior results; errors stay sanitized.
- **Scope boundary:** Testing must not start enrichment or create graph evidence.
- **Owned by:** Task #45 (Verify a connector automatically after its credential
  is saved) and Task #46 (Prevent simultaneous connector checks from overwriting
  each other); connector list/mutation recovery is included in Task #84. Task #78
  (Evaluate Integration And Operations) validates the operator journey.

### UX-11 — Direct Export can silently deliver an incomplete package

- **Severity:** High
- **Personas:** Integration partner; acquisition/program decision-maker;
  operator/auditor
- **Evidence:** `web/src/App.vue`; `api/illuminate/routers/exports.py`;
  `docs/INSIGHT_EXPORT.md`
- **Acceptance:** Product UI shows scope, schema version, count, filters,
  lifecycle/simulation handling, pagination/watermark, supported formats,
  progress, completion, empty, and failure. A “complete download” follows all
  pages or is explicitly labeled bounded/partial.
- **Scope boundary:** Preserve current versioned export protocol and permission
  boundaries.
- **Owned by:** [Task #64 (Expose Findings Interoperability)](../.local/tasks/expose-findings-interoperability.md),
  Task #50 (Gate The Judge Journey), and Task #78 (Evaluate Integration And
  Operations).

## Cross-persona synthesis

### Shared root causes

1. **Context is stored per surface rather than treated as one journey.** Program,
   vendor, finding, evidence, and compare selections drift across routes.
2. **The product exposes implementation models before user questions.** Internal
   IDs, graph depth/layers, claim predicates, event IDs, MCP, and pagination
   headers appear before plain-language outcomes or guidance.
3. **State dimensions are collapsed into one badge.** Approval, verification,
   freshness, derivation, and simulation need a consistent shared vocabulary.
4. **Happy-path depth is stronger than recovery.** The application often has the
   evidence or diagnostic detail, but failures and retries are uneven.
5. **Analyst density is used as the default.** The mission page demonstrates the
   right progressive-disclosure direction; graph and portfolio do not yet follow
   it.

### Role-specific preferences, not global defects

- Acquisition users prefer concise decision cards; analysts need dense evidence.
  Both are valid when detail is progressively disclosed.
- Supply-chain analysts benefit from graph controls that should remain available
  even if hidden initially.
- Operators need raw diagnostics and IDs in settings; these should not dominate
  the judged mission.
- Integration partners can use technical schema/watermark language when the
  product also explains safe defaults and completeness.
- Light versus dark preference is not a defect; inconsistent theme application
  and unreadable contrast are.

## Preserved strengths

- Keep the mission question and “choose the question—not the navigation”
  structure.
- Keep risk separate from confidence, completeness, and freshness.
- Keep missing evidence from appearing as zero risk.
- Keep simulation visible through repeated text and non-color graph styles.
- Keep deterministic presets and frozen comparison independent of live services.
- Keep Programs’ explicit loading, empty, failure, validation, and recovery
  pattern as the model for secondary routes.
- Keep exact source/retrieval/method/rule detail available to analysts.
- Keep catalog writes server-side, permission-gated, confirmed, and visibly
  different from dry runs.

## Completion criteria for downstream work

The overall journey may be called ready only after:

1. Tasks #59–61 preserve mission/finding context while simplifying navigation,
   graph, and portfolio.
2. Task #63 keeps system recommendation, claim review state, and human decision
   visibly separate.
3. Task #64 exposes bounded versus complete export behavior and lifecycle
   semantics in-product.
4. Tasks #84–86 close exact-evidence/recovery, lifecycle-label, and unsupported
   reassurance defects.
5. Task #50 passes deterministic keyboard, focus, accessible-name, failure,
   responsive, zoom, theme, and download checks.
6. Tasks #75–78 run the five shared persona scenarios against the merged build
   and reconcile any role-specific residuals without duplicating this register.
7. Task #21 records two clean rehearsals with a non-expert first finding under 60
   seconds and intentional vendor comparison under three minutes.
