# Six-minute judge demo and release rehearsal

Use this as the presenter script, failure card, and release record. The published
weights are intentionally preserved as **30/25/20/15/10/1 = 101%**.

## Mission question

> Which vendors can this program trust—and where is the supply chain exposed?

Illuminate answers with traceable decision support, not an eligibility decision:
find the path, inspect the evidence and truth state, compare vendor risk, and
export a versioned finding for another consumer.

## Timed script (6:00)

| Time | Presenter action and exact claim | Rubric |
|---|---|---|
| 0:00–0:30 | **Presenter A — Mission.** Open a clean session at `/`. “A program analyst needs the first actionable exposure quickly without confusing missing evidence with safety.” Point to readiness, source coverage, and the one-click **Find supply exposure** action. | Mission impact **30**; usability **20** |
| 0:30–1:30 | Open the deterministic supply-exposure graph. Select a supplier path and show source/evidence details. “The graph links program, supplier, ownership, geography, and people; every asserted fact can resolve through a claim to an artifact.” State that the orange adversarial chain is simulated and visibly labelled, not historical fact. | Mission impact **30**; technical innovation **25** |
| 1:30–2:15 | Use the named sole-source/foreign-control lens; show the executed query. “Named templates work without an LLM. Generated Cypher, when enabled, is allowlisted, hop-bounded, read-limited, and shown to the analyst.” | Innovation **25**; security and sustainability **15** |
| 2:15–3:05 | **Handoff: A → B:** “We found the path; now [B] shows how it changes triage.” Open `/portfolio`, select a vendor, and show score, completeness, freshness, categories, recommendation, and citations. “Deterministic rules own the score and recommendation; AI may summarize approved findings but cannot create evidence or change the score.” | Mission impact **30**; usability **20** |
| 3:05–3:45 | Follow one finding to its evidence. Use the architecture/lineage visual below if the live inspector is slow. “Connector results are claims first. Trust or human review commits them; rejected and simulated material remain distinguishable.” | Innovation **25**; security and sustainability **15** |
| 3:45–4:25 | Show a write preview or the prepared permission-dialog image in `details.html`. “Reads and writes share one contract across chat and MCP. Writes run in a rolled-back preview, disclose impact, and wait for explicit approval; credentials remain server-side and encrypted at rest.” | Security and sustainability **15**; interoperability **1** |
| 4:25–5:05 | Show the versioned findings/export and NDIA catalog preview/dry run. “Stable IDs, typed paths, provenance, truth/simulation status, pagination, and watermarks let consumers integrate without our Vue UI or Neo4j serialization. Catalog metadata describes the export; it does not duplicate evidence.” | Interoperability **1**; collaboration **10** |
| 5:05–5:35 | **Handoff: B → A:** “The consumer contract is portable; [A] closes on delivery.” Show the architecture brief’s Replit and Docker paths. “One artifact/claim boundary lets teammates add connectors and analytics independently; one tool contract serves UI and agents.” | Collaboration **10**; sustainability **15** |
| 5:35–6:00 | State limitations and close: “This prototype uses public data with variable coverage, one explicitly simulated scenario, and development deployment controls. It is not an adjudication, operational calibration, exhaustive source coverage, or accreditation. Illuminate turns an opaque supplier question into a traceable, reviewable decision path—and makes that path reusable by any consumer.” | All criteria |

### Architecture and lineage visual

```text
public sources → Artifact → Claim ──trust/review──→ graph fact
                                      │                 │
                                      └ truth state     └ claim_id → source
graph fact → deterministic finding → score/recommendation → versioned export
       UI/chat ─┐                                      ┌─ partner consumer
external MCP ──┴─ one bounded tool contract           └─ NDIA catalog metadata
```

The fuller visual, trust boundaries, production-hardening list, and judge answers
are in [`architecture-lineage-brief.md`](architecture-lineage-brief.md).

## Failure drill card

Never troubleshoot an optional service on stage. Say the cue, take the listed
fallback, and continue on the same rubric claim.

| Forced failure | Visible cue | Deterministic fallback and presenter line |
|---|---|---|
| LLM unavailable/timeout | Chat/model action errors or no key is configured | Use a named graph lens and deterministic report summary. “The model is optional: templates still retrieve the graph, and deterministic code still owns evidence, scoring, and recommendation.” |
| Live connector timeout/error | Readiness reports optional degradation or a source attempt reports a safe error | Continue with retained source artifacts and stamped mission data; show retrieval time and coverage. “A failed refresh does not erase already attributable evidence, and absence is not treated as safety.” |
| NDIA catalog write rejected/unconfigured | Submit returns a safe 4xx/5xx or publication is not configured | Show preview, schema-valid dry run, and versioned export; do **not** claim publication. “The consumer data product remains available. Catalog publication is separately authorized and idempotent, so a portal failure cannot corrupt findings or trigger blind duplicate writes.” |

Executable drills:

```bash
cd api
uv run --extra dev --frozen pytest -q \
  tests/test_ai_summary_guardrails.py::test_http_summary_timeout_returns_and_persists_deterministic_fallback \
  tests/test_fault_injection_recovery.py::test_optional_connector_timeout_preserves_deterministic_readiness \
  tests/test_catalog.py::test_missing_credential_fails_safe \
  tests/test_catalog.py::test_preview_and_confirmed_dry_run_are_schema_valid
```

## Likely judge questions: short answers

- **Is a “no hit” proof a vendor is safe?** No. It means only that the named
  source produced no match at the recorded time and under the recorded method.
- **Where can AI be wrong?** Intent, tool selection, generated query, or prose.
  Tools are bounded, queries are validated and visible, and AI is not evidence
  or scoring authority.
- **Why a graph?** The risk is in multi-tier paths and shared ownership/people,
  while claims and artifacts preserve the provenance of each traversed fact.
- **Can another system consume this?** Yes: use the versioned finding export or
  bounded MCP tools; consumers do not need the frontend or Neo4j wire format.
- **Is it production accredited?** No. The demo shows design controls and
  portable deployment, not ATO, CMMC, FedRAMP, or classified-data approval.
- **What hardening remains?** Enterprise identity/RBAC, managed key rotation,
  TLS and segmentation, immutable audit/retention, egress/rate controls,
  monitoring/DR, supply-chain scans, governance, and authorization testing.

## Clean-session rehearsal and release checklist

Run the application workflow first. Each pass creates a new Chromium profile,
follows the mission page's rendered supply-exposure action with its program
scope, requires the named lens to complete, requires usable vendor assessments
from that program's portfolio, and fails if same-origin API routing breaks or
the technical journey exceeds 360 seconds.

```bash
rm -rf rehearsal-results/pass-1 rehearsal-results/pass-2
REHEARSAL_OUTPUT_DIR=rehearsal-results/pass-1 scripts/rehearse-demo.sh
REHEARSAL_OUTPUT_DIR=rehearsal-results/pass-2 scripts/rehearse-demo.sh
scripts/test-rehearse-demo.sh # proves a stalled mission lens cannot pass
```

Before release:

- [ ] Health says `ok: true` and `primary_workflow_ready: true`.
- [ ] Two consecutive clean-profile technical passes succeed.
- [ ] Two presenters read the timed script aloud in 6:00 or less; handoffs land
  at 2:15 and 5:05.
- [ ] LLM, connector, and catalog tests above pass.
- [ ] Simulation badges, evidence source/time, and executed query are visible.
- [ ] No presenter claims exhaustive coverage, adjudication, calibration,
  accreditation, or successful catalog publication without a success receipt.
- [ ] Architecture brief and `details.html` are open as offline visual backups.
- [ ] Secrets, browser notifications, unrelated tabs, and developer consoles are hidden.
- [ ] Release revision and health response are recorded with the rehearsal.

## Fallback recording

Record one local 1080p browser capture while reading the same script. Begin and
end on the mission page; keep the graph, portfolio, evidence inspector,
permission-dialog backup, and export/catalog dry run in the recording. Do not
record connector keys or settings. Name it
`illuminate-demo-YYYYMMDD-HHMM-<short-revision>.mp4`, verify audio and duration,
and keep a second local copy. The recording is a release artifact, not evidence
that an unrecorded live connector or catalog publication succeeded.

## Rehearsal record

| Pass | Clean profile | Technical path | Duration | Forced failures | Spoken pass |
|---|---|---|---|---|---|
| 1 · 2026-09-08 | PASS | PASS: mission action → scoped finding → assessed portfolio | 22s / 360s | PASS: 4 focused tests; stalled lens rejected | Script allocates exactly 6:00; named handoffs at 2:15 and 5:05 |
| 2 · 2026-09-08 | PASS | PASS: mission action → scoped finding → assessed portfolio | 9s / 360s | PASS: same unchanged test run | Script allocates exactly 6:00; named handoffs at 2:15 and 5:05 |

The measured durations are automated technical-path times, not a claim about a
presenter's speaking pace. The release operator must still check the spoken-pass
box above before recording or presenting; that team-specific sign-off cannot be
manufactured by the software harness.
