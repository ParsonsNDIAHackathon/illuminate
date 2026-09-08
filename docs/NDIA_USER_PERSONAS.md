# NDIA user personas and evaluation scenarios

## Purpose and evidence basis

These role-based personas give independent reviewers a consistent way to evaluate
Illuminate for its two primary NDIA missions:

- **Use case 7 (UC-7), Defense Supply Chain Illumination:** identify hidden
  supplier, ownership, concentration, and readiness dependencies.
- **Use case 11 (UC-11), Automated Vendor Risk Assessment:** prioritize vendors
  for proportionate review using a standardized, evidence-backed risk profile.

The set also covers the operational and interoperability work required to use
those findings safely. It is grounded in the mission workflow, the implemented
artifact-to-claim-to-graph lineage, the findings export contract, the
single-workspace deployment boundary, and the current guided V-22 demonstration.
The names below are role labels, not demographic profiles.

All five personas share one authority boundary:

> Illuminate provides evidence-backed decision support. It may prioritize
> investigation, diligence, monitoring, or sourcing research; it does not
> determine eligibility, make an award decision, establish an intelligence
> conclusion, or autonomously adjudicate a vendor.

## Terms every evaluator should preserve

| Term | Meaning in an evaluation |
| --- | --- |
| **Provenance** | The source identity, record or URL, retrieval time, method, quality and usage notes, and the claim/artifact chain supporting a result. |
| **Confidence** | Strength of support for a particular assertion or match. It is not source coverage and is not a probability that a vendor is compromised. |
| **Completeness** | How much relevant evidence or source coverage is present. Missing evidence creates a gap; it does not lower risk or prove safety. |
| **Freshness** | When evidence was retrieved or last updated, considered alongside source reporting lag. A precise old record may still be stale. |
| **Truth state** | Whether an assertion is staged, committed/approved, rejected/disputed, or a scenario. Only the applicable state may drive a verified finding. |
| **Simulation** | Synthetic scenario content. If a material input is simulated, every derived finding remains visibly simulated regardless of confidence. |

## Persona map

| Persona | Primary journey | Decision contribution | Must not be asked to do |
| --- | --- | --- | --- |
| Acquisition/program decision-maker | UC-7 with UC-11 decision context | Set review and sourcing priorities; request diligence or contingency analysis | Adjudicate from a score or treat coverage gaps as proof of safety |
| Supply-chain or logistics analyst | UC-7 | Explain dependency paths and readiness exposure; identify research priorities | Invent alternates, criticality, capacity, or lead time |
| Counterintelligence/vendor-risk analyst | UC-11 with UC-7 ownership context | Review evidence, resolve leads, and recommend proportionate diligence | Convert a name match, media report, or simulated tie into an accusation |
| Data-integration partner | Supporting interoperability journey | Safely consume and synchronize versioned findings into another system | Scrape the UI/graph serialization or discard lifecycle and lineage fields |
| Deployment/data operator | Supporting operational journey | Keep the bounded demo workflow ready, observable, and safely configured | Claim production accreditation or conceal degraded dependencies |

---

## Persona 1: Acquisition/program decision-maker

**Primary mapping:** UC-7, consuming UC-11 recommendations.

**Mission goals**

- Understand which supplier or ownership dependencies could affect program
  readiness and which issue warrants action first.
- Compare vendors under one transparent framework and choose an appropriate next
  step: proceed, proceed with controls, enhanced diligence, hold for review, or
  alternate-source research.
- Brief leadership with a concise conclusion that remains traceable to evidence.

**Triggering scenario**

A program review identifies a sole-source or concentrated dependency in the
V-22/PMA-275 supplier network. The decision-maker needs to understand whether a
hidden ownership path changes the program's diligence or contingency priorities.

**Primary workflow**

1. Start the guided mission and confirm program scope, source coverage,
   freshness, and whether scenario data is included.
2. Review the highest-priority readiness finding and its plain-language path.
3. Compare the affected vendor with a lower-risk vendor under the same rules.
4. Inspect the recommendation, evidence completeness, confidence, and gaps.
5. Assign a human next step without treating the output as an award decision.

**Domain knowledge**

Understands program priorities, acquisition gates, supplier criticality, and the
consequences of schedule or sourcing disruption. May not know Cypher, graph
modeling, connector behavior, or the details of every public source.

**Information needs**

- Affected program, award, supplier tier, component/category, and financial or
  operational exposure where supported.
- Severity and recommended action, separated from confidence and completeness.
- A short, typed path explaining the hidden dependency.
- Known alternatives and criticality, or an explicit statement that they are
  unknown.
- Source coverage, retrieval dates, truth state, and simulation labels.

**Trust and evidence expectations**

Every material conclusion must open to its rule, path, and evidence. The
decision-maker expects the same scoring rules for both comparison vendors and a
clear explanation that a “no hit” is source-specific, not a safety
determination. AI prose may summarize but cannot create facts or change scores.

**Constraints and failure concerns**

Time is limited and the first screen must support rapid triage. Dense analyst
detail should not obscure the mission consequence. The most dangerous failures
are an unlabeled simulated allegation, false precision in a score, a recommendation
without evidence, or an unknown alternate source presented as nonexistent.

**Measurable success signals**

- Reaches one actionable finding in under 60 seconds.
- Explains the affected program, dependency, evidence state, and next human
  action without equating the score with adjudication.
- Reaches and interprets the risky/trustworthy comparison within three minutes.
- Correctly distinguishes risk, confidence, completeness, and simulation.

### Reviewer scenario

**Start condition:** Open a clean session at the guided mission entry point with
the deterministic V-22 data available.

**Tasks**

1. State the mission question and identify the current program scope.
2. Find the dependency with the greatest apparent readiness concern.
3. Explain, in one sentence, why it is highlighted and what evidence state it
   has.
4. Compare the affected vendor with the trustworthy comparison vendor.
5. Choose the next review or sourcing action and name one fact that would be
   needed before an actual acquisition decision.

**Expected outcome:** The reviewer forms a defensible priority and human follow-up
without declaring a vendor eligible, ineligible, trustworthy, or compromised.

**Comprehension checks**

- Does a high score mean the vendor must be excluded? **No.**
- Does missing alternate-source data prove the supplier is sole source? **No; it
  is a diligence gap unless a supported sole-source fact exists.**
- Can simulated evidence be briefed as a real allegation? **No.**

---

## Persona 2: Supply-chain or logistics analyst

**Primary mapping:** UC-7.

**Mission goals**

- Reveal deep-tier suppliers, ownership/control paths, concentration,
  sole-source exposure, shared leadership, and geographic dependencies.
- Translate graph structure into a specific readiness implication.
- Identify the next data collection or alternate-source question when the graph
  cannot support a conclusion.

**Triggering scenario**

A critical program depends on a supplier that appears ordinary at the contract
level, but the analyst suspects hidden upstream control or a single point of
failure that is not visible in the prime award record.

**Primary workflow**

1. Open the program graph and inspect supplier tiers and award context.
2. Run or select the relevant supply-chain, foreign-parent, interlock,
   concentration, or sole-source view.
3. Follow the typed path from program/award through supplier to parent, person,
   geography, or evidence.
4. Check source count, retrieval time, confidence, completeness, and truth state.
5. Record the readiness implication and unresolved intelligence gaps.

**Domain knowledge**

Comfortable with bills of material, supplier tiers, sourcing concentration,
logistics dependencies, contract context, and contingency planning. Can reason
over a graph but should not need to know its storage schema.

**Information needs**

- Supplier depth, upstream/downstream dependencies, and relationship types.
- Award, category, location, sole-source, concentration, and alternate-source
  evidence.
- Entity identifiers and match method to detect mistaken joins.
- The rule behind each derived finding and all contributing claims.
- Explicit unknowns for component criticality, capacity, lead time, tier depth,
  and alternate sources.

**Trust and evidence expectations**

Graph edges are not self-authenticating. The analyst expects each material edge
to trace to a current backing claim and artifact, and derived findings to retain
their typed path. Simulation must be visually contagious through the entire
path. Uneven sub-award coverage must remain visible.

**Constraints and failure concerns**

Public data is incomplete, delayed, and inconsistent across identifiers. The
analyst fears a false bridge between programs, an ambiguous entity silently
merged, stale ownership represented as current, or a graph visualization that
hides why a path matters.

**Measurable success signals**

- Reconstructs the highlighted path and distinguishes supply, ownership/control,
  person, location, and evidence relationships.
- Names the supported readiness concern and at least one unsupported unknown.
- Opens the source lineage for every material step in the conclusion.
- Does not infer complete tier coverage or an alternate source from absence.

### Reviewer scenario

**Start condition:** Begin at the V-22 program view, not at a preselected entity
report.

**Tasks**

1. Locate a concentrated or sole-source dependency.
2. Follow its path to any parent/control entity or shared leader.
3. Verify the identity method and supporting evidence for the material
   relationships.
4. Determine which path elements are approved, staged, rejected, or simulated.
5. Write a two-sentence readiness implication and a concrete next collection or
   sourcing question.

**Expected outcome:** The reviewer produces a traceable dependency explanation
and a bounded research priority, not an invented supply-chain fact.

**Comprehension checks**

- Is every visible relationship an approved real-world fact? **No; inspect truth
  and simulation state.**
- Does high match confidence imply complete supplier coverage? **No.**
- If capacity or lead time is absent, may the reviewer estimate it from the risk
  score? **No.**

---

## Persona 3: Counterintelligence/vendor-risk analyst

**Primary mapping:** UC-11, using UC-7 ownership and dependency context.

**Mission goals**

- Triage vendors consistently across ownership/control, financial health,
  litigation/legal, sanctions/regulatory/debarment, cybersecurity, adverse
  media, and supply criticality.
- Separate supported facts from leads, analyst judgments, missing data, and
  simulation.
- Recommend proportionate diligence while minimizing false positives and
  unsupported allegations.

**Triggering scenario**

Two program vendors require review. One has a high-risk ownership path and
adverse indicators; the other has fewer indicators but uneven source coverage.
The analyst must prioritize work without treating missing records as exculpatory.

**Primary workflow**

1. Filter or rank the vendor portfolio by severity, category, completeness,
   freshness, tier, and truth/simulation state.
2. Compare both vendors under the same scoring framework.
3. Open every nonzero category factor and inspect its rule and evidence.
4. Review fuzzy matches and staged claims; commit or reject only when authorized
   and supported.
5. Record a disposition recommendation and unresolved diligence tasks.

**Domain knowledge**

Understands vendor due diligence, ownership and control, sanctions and
debarment screening, adverse-media limitations, source reliability, and
false-positive management. Understands that open-source indicators are leads,
not intelligence adjudications.

**Information needs**

- Overall score and band with versioned weights and category contributions.
- Evidence count, confidence, completeness, freshness, and missing-data flags
  displayed separately.
- Stable identifiers, entity-resolution method, ambiguity, source jurisdiction,
  and retrieval date.
- Claim lifecycle, analyst decision history, provenance, and simulation status.
- A plain-language rationale and recommended human action.

**Trust and evidence expectations**

Every nonzero factor needs evidence or an explicit analyst-judgment label.
Negative screening means only that the named source returned no match under the
recorded method and time. Rejected or staged claims cannot silently influence an
approved finding. AI output is reviewable summary, never evidence.

**Constraints and failure concerns**

Adverse media and name matches are noisy; source coverage varies by jurisdiction
and prominence. Key concerns are false accusations, duplicated entities,
stale screening results, hidden score weights, missing data that lowers risk,
and claim decisions whose downstream effects do not match their status.

**Measurable success signals**

- Explains every nonzero factor using its rule and evidence.
- Identifies at least one difference between confidence and completeness.
- Produces a proportionate disposition and diligence list without an autonomous
  adverse decision.
- Detects and declines to rely on a staged, rejected, ambiguous, or simulated
  item as approved fact.

### Reviewer scenario

**Start condition:** Open the portfolio or vendor comparison with one higher-risk
and one lower-risk vendor.

**Tasks**

1. Explain why the vendors have different scores using category contributions.
2. Trace one ownership/control factor and one screening, legal, cyber, financial,
   or adverse-media factor to evidence.
3. Identify any stale, incomplete, ambiguous, staged, or simulated input.
4. Decide which vendor enters enhanced diligence first and list the evidence
   needed to resolve one gap.
5. State what the interface does and does not establish about the vendor.

**Expected outcome:** The reviewer creates a defensible review queue and
diligence rationale while preserving uncertainty and lifecycle state.

**Comprehension checks**

- Is a source “no hit” proof that a vendor is safe? **No.**
- May AI-generated prose promote a staged claim or modify the score? **No.**
- Does a score represent the probability of compromise? **No; it is a
  transparent prioritization rule.**

---

## Persona 4: Data-integration partner

**Primary mapping:** Supporting interoperability journey for UC-7/UC-11 and
partner use cases.

**Mission goals**

- Retrieve Illuminate findings without depending on its Vue interface or Neo4j
  representation.
- Join findings to planning, due-diligence, fusion, or analyst systems using
  stable identifiers.
- Synchronize updates repeatably while preserving handling, lineage, and
  simulation semantics.

**Triggering scenario**

A partner team wants supplier-risk findings in its own application and must
perform a full load followed by incremental updates without creating duplicates
or turning scenario records into verified intelligence.

**Primary workflow**

1. Discover the live API and negotiate the published schema version.
2. Retrieve and validate a full JSON or NDJSON findings snapshot.
3. Upsert by stable finding ID and join subjects using UEI, CAGE, LEI, award ID,
   or another declared identifier rather than names.
4. Follow pagination and commit the final watermark atomically.
5. Apply incremental updates while retaining provenance, classification,
   lifecycle, completeness, confidence, freshness, and simulation fields.

**Domain knowledge**

Comfortable with APIs, JSON Schema, pagination, idempotent upserts, data quality,
classification/handling rules, and schema-version compatibility. Does not need
to know the internal graph schema.

**Information needs**

- Contract/schema version, generation time, documentation, sample payload, and
  quality/limitation notes.
- Stable finding and subject identifiers, typed paths, recommendation, and
  update time.
- Opaque cursor and watermark behavior, including recovery from expiration.
- Provenance, licensing/usage, classification, truth state, completeness,
  confidence, freshness, and simulation.
- Catalog contribution status distinguished as published, pending, or validated
  dry run.

**Trust and evidence expectations**

The published schema and running OpenAPI document are authoritative. A finding
without its lineage is incomplete. The consumer must enforce the most
restrictive handling rule and treat simulation and truth state as stronger
constraints than numeric confidence.

**Constraints and failure concerns**

The partner cannot rely on record order, display names, frontend serializers,
internal Neo4j IDs, or a permanent cursor. Key failures are duplicate findings,
silent schema drift, advanced watermarks after partial ingestion, lost nested
provenance in CSV, and scenario data entering verified workflows.

**Measurable success signals**

- Validates a snapshot against the advertised schema.
- Replays the same page without duplicate records and correctly upserts an
  updated finding.
- Advances a watermark only after all pages commit.
- Preserves all safety fields and excludes simulated records from a
  verified-intelligence view.
- Recovers from an incompatible watermark by taking a new full snapshot.

### Reviewer scenario

**Start condition:** Use the API documentation and interoperability guide; do not
inspect application internals.

**Tasks**

1. Retrieve the schema and one complete page of findings.
2. Select safe join keys and explain why the display name is insufficient.
3. Load all pages, store the final watermark, then request an incremental sync.
4. Demonstrate idempotent handling of an existing finding ID.
5. Show how a simulated or non-approved record is retained but prevented from
   entering a verified workflow.

**Expected outcome:** Another system consumes Illuminate as a versioned data
product without weakening its meaning or depending on its UI.

**Comprehension checks**

- Is the drawn subgraph a durable export contract? **No.**
- Does `confidence: 1.0` make a simulated scenario true? **No.**
- Should a consumer append every incremental record? **No; upsert by stable ID.**

---

## Persona 5: Deployment/data operator

**Primary mapping:** Supporting operational journey for UC-7/UC-11.

**Mission goals**

- Keep the deterministic mission path ready and explain which optional
  dependencies are degraded.
- Manage public-source ingestion, credentials, graph state, claim review
  controls, and safe catalog publication.
- Diagnose failures without leaking secrets, raw payloads, or false completion.

**Triggering scenario**

Before a mission review, the operator must confirm that the API, Neo4j, seed
version, graph counts, exports, and guided workflow are healthy while an optional
connector or model service is unavailable.

**Primary workflow**

1. Check readiness for API, graph, seed state, source coverage, and optional
   services.
2. Confirm the deterministic V-22 workflow, reports, claim review, and exports
   work without live model or connector access.
3. Inspect bounded connector diagnostics and distinguish unavailable, stale,
   partial, and complete states.
4. Protect credentials and keep graph writes behind preview and explicit
   approval.
5. Preview and validate catalog metadata; publish only with configured
   organizer-provided paths and explicit human confirmation.

**Domain knowledge**

Understands service health, logs, backups, credentials, data refreshes, source
quotas, deployment boundaries, and recovery. Knows the difference between
demonstration readiness and production accreditation.

**Information needs**

- Health of required versus optional services and the reason for degradation.
- Seed version, graph counts, source coverage/freshness, job state, and bounded
  error categories.
- Credential configuration state without secret values.
- Backup/restore consequences and confirmation of destructive operations.
- Export validation and catalog dry-run/publish status, identity, and
  idempotency.

**Trust and evidence expectations**

Failures must be explicit and must not manufacture successful results. Logs,
responses, exports, cached URLs, and catalog metadata must contain no secrets or
restricted raw payloads. Simulation labels and claim lifecycle must survive
refresh, restart, export, and recovery.

**Constraints and failure concerns**

Illuminate is a single-workspace, unclassified demonstration system with local
state and optional external services. It is not an authorization boundary or a
claim of ATO, CMMC, FedRAMP, classified-data approval, or production
availability. The operator fears partial startup presented as healthy, runaway
queries or retries, destructive reseeding, credential leakage, stale status,
and duplicate catalog publication.

**Measurable success signals**

- Correctly separates primary-workflow readiness from optional-service health.
- Completes the deterministic mission path during a forced model or connector
  failure and accurately communicates the limitation.
- Confirms writes require preview/approval and destructive actions require
  acknowledgement.
- Produces a schema-valid catalog dry run when write access is unavailable,
  without claiming publication.
- Finds no credentials in browser responses, ordinary logs, exports, or catalog
  metadata.

### Reviewer scenario

**Start condition:** The application is running with seeded data; at least one
optional live connector or model dependency is unavailable.

**Tasks**

1. Determine whether the primary mission workflow is ready and cite the health
   evidence.
2. Run the guided path and one export without the unavailable dependency.
3. Explain the resulting source coverage and freshness limitations to an
   analyst.
4. Preview a graph write and verify that it cannot commit without authorization.
5. Generate a catalog contribution dry run and identify what additional
   configuration and confirmation publication would require.

**Expected outcome:** The operator keeps the useful deterministic workflow
available, reports degraded capabilities honestly, and preserves all security
and human-control boundaries.

**Comprehension checks**

- Does an unavailable optional connector make the seeded mission path unready?
  **Not by itself.**
- Is a valid catalog dry run a published dataset? **No.**
- Does successful local or Replit startup establish production accreditation?
  **No.**

## Cross-persona usability principles

1. **One truth, progressively disclosed.** Executive summaries, analyst paths,
   operator diagnostics, and machine records must be views of the same finding,
   not separately authored conclusions.
2. **Consequence before complexity.** Start with mission impact and recommended
   human action; reveal score factors, typed paths, claims, artifacts, rules, and
   raw diagnostics on demand.
3. **Keep risk dimensions independent.** Risk, confidence, completeness,
   freshness, truth state, and simulation must remain separately visible and
   must never be collapsed into one reassuring number.
4. **Unknown is a valid result.** Missing alternates, criticality, tier depth,
   capacity, lead time, or source coverage should create an explicit research
   task rather than a guessed value.
5. **Lineage travels with the conclusion.** A user should be able to move from
   recommendation to factor to path to claim to artifact/source. A machine
   consumer must receive equivalent lineage in the export.
6. **Human authority remains visible.** Recommendations route work; authorized
   people review ambiguous matches and claims and make procurement or
   intelligence decisions.
7. **Deterministic core, optional enhancement.** Guided analysis and exports
   remain useful without a live model or connector. AI explains structured
   results but does not create evidence or scores.
8. **Simulation is contagious.** Scenario state propagates through every
   derived result, visualization, comparison, and export.

## Intentional tensions and interface response

| Tension | What each role needs | Intentional response |
| --- | --- | --- |
| Executive clarity vs. analyst depth | Decision-makers need a rapid priority; analysts need paths, rules, ambiguity, and source detail. | Use a concise finding and action first, with direct drill-down to the unchanged underlying lineage. |
| Analyst depth vs. operator diagnostics | Analysts need evidence meaning; operators need connector, job, seed, and service state. | Keep evidence quality and source freshness in the analytic view; keep infrastructure detail in readiness/operations views without hiding impact. |
| Human readability vs. machine precision | People need plain language; consumers need stable IDs, exact enums, versions, cursors, and nested lineage. | Generate both from one versioned finding contract; do not ask consumers to parse prose or scrape the UI. |
| Fast triage vs. uncertainty | Users want ranking; public-source coverage cannot justify certainty. | Rank transparently while placing completeness, freshness, truth, and simulation beside severity—not behind a generic details screen. |
| Scenario value vs. reputational safety | A simulated hidden tie demonstrates the workflow but could be mistaken for an allegation. | Badge scenario content at every level and require reviewers to state its status when explaining a finding. |
| Availability vs. live freshness | Deterministic fixtures keep the mission usable; live enrichment may be newer. | Show fixture/live source and retrieval time explicitly, keep live calls optional, and report stale or unavailable states without fabrication. |

## Evaluation recording template

Downstream reviewers should record the following for each persona:

- persona and mapped journey;
- start condition and data/simulation state;
- task completion and elapsed time;
- conclusion or artifact produced;
- evidence path successfully traced;
- interpretation of risk, confidence, completeness, freshness, truth state, and
  simulation;
- any point where the reviewer invented a requirement or needed undocumented
  help;
- observed failure, severity, and the persona's mission consequence.

This document defines evaluation roles and tasks; it does not report usability
results or expand Illuminate's authority beyond an unclassified,
evidence-backed decision-support demonstration.