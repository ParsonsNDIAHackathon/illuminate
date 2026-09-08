# Acquisition Decision Journey Review

**Review date:** 2026-09-08  
**Build:** `2ce85ec`  
**Environment:** Replit development workflow `UC7 Illuminate`  
**Program:** V-22 Osprey Program (PMA-275), `ent_6484d4d13b76`  
**Seed:** deterministic `uc7-fixtures-v1`; offline and scenario flags set  
**Operational state:** rehearsal workflow ready; live operational refresh not ready; source coverage 0; freshness unknown

## Persona and decision boundary

This review adopted the acquisition/program decision-maker in
`docs/NDIA_USER_PERSONAS.md`: a time-constrained user who understands program
priorities and supplier disruption but should not need Cypher or graph-model
knowledge. The reviewer needed to identify the most important readiness
dependency, understand why it was credible, compare it under a common vendor-risk
framework, and choose a human follow-up without making an award, eligibility, or
intelligence determination.

The comprehension boundary was:

- a risk score prioritizes review; it does not require exclusion;
- missing alternate-source data does not prove sole-source status;
- confidence, completeness, and freshness answer different trust questions;
- simulated evidence cannot become a real allegation; and
- a recommendation remains advisory and separate from claim truth and human
  disposition.

## Tested journey and timings

The reviewer opened a clean browser session and followed the visible acquisition
workflow: mission entry → Find supply exposure → program-scoped portfolio →
risky/trustworthy comparison → live vendor risk report → committed claims.

| Checkpoint | Measured result | Persona outcome |
| --- | ---: | --- |
| Mission entry ready | 0.682 s | Program scope was immediate. Evidence mode was not: the page said `Mission ready` while source coverage was 0 and freshness was unknown. |
| Guided supply-exposure graph | 0.810 s | The graph rendered well inside the five-second system budget. |
| First actionable readiness finding | Not reached at the 60 s checkpoint | Failed. The completion message reported `9 graph elements` but did not name an affected supplier, component/category, readiness implication, evidence state, or next action. |
| Program portfolio | 0.430 s to initial ranked view | Risk and evidence quality were visibly separated, but the reviewer had to leave the graph and infer which row represented its result. |
| Risky/trustworthy comparison | 3.980 s elapsed from mission start | Passed the three-minute threshold. The frozen profiles were aligned, easy to contrast, and unmistakably simulated. |
| Live Subaru recommendation | 0.369 s route render | `complete diligence`, 29% completeness, five explicit category gaps, and separate human disposition were understandable. |
| Committed claim inspection | 7 scoped claims loaded | Passed. Source, method, confidence, retrieval time, evidence kind, and truth state remained visible. |

Timings are browser-navigation and render measurements from the live development
workflow. The first-action result is intentionally recorded as a failed persona
threshold rather than treating fast graph rendering as successful comprehension.

## Scenario outcome

### 1. Entry and data mode

The entry clearly stated the mission question, selected the V-22 program, showed
the deterministic workflow, and included a strong simulation boundary. However,
the same screen displayed:

- `Mission ready`;
- source coverage `0`;
- freshness `UNKNOWN`; and
- an advisory that the database was ready while live refresh might continue.

The readiness contract identified the seed as both offline and scenario data and
reported `operational_live_ready: false`, but those mode distinctions were not
summarized in the decision card. A decision-maker can therefore tell that
simulation exists, but cannot quickly tell whether the selected program is a
frozen rehearsal baseline or live operational evidence.

### 2. Program exposure and readiness

The guided supply-exposure action correctly retained the V-22 scope, showed a
simulation badge, highlighted manufacturing-in-China paths, and exposed supplier
tier and relationship legends. Its only result summary was:

> Supply exposure analysis complete · 9 graph elements

That is not an actionable acquisition finding. Without analyst-level graph
knowledge, the reviewer could not answer which dependency threatened readiness,
why it ranked first, whether a sole-source or concentration fact was supported,
or what to do next. This validated issue is already covered by Task #60
(Simplify Graph Workspace), whose acceptance criteria require every preset to end
with an affected program/vendor, path, risk or gap, truth/simulation state, and
next action. No duplicate task was created.

### 3. Portfolio triage

The program-scoped portfolio separated assessed risk from confidence,
completeness, freshness, and diligence flags. Loading and unavailable reports
were not presented as zero risk, and identity cues remained available.

The decision continuity was only partial: because the graph did not name its
affected vendor, the reviewer had to reinterpret the portfolio independently.
That break should close when Task #60 supplies a direct, actionable graph result.

### 4. Vendor comparison

The judged comparison was the clearest acquisition surface:

| Measure | Atlas Precision Systems | Vanguard Critical Components |
| --- | --- | --- |
| Score / band | 0 / low | 100 / critical |
| Confidence | 96% | 91% |
| Completeness | 100% | 100% |
| Freshness | current | diligence required |
| Disposition | standard monitoring | hold and escalate |
| Simulation | conspicuous | conspicuous |

The page stated that scores prioritize review and are not proof of wrongdoing.
Both profiles used the same framework and category order. Stale evidence created
a required refresh rather than appearing current. The reviewer correctly
understood that this was simulated calibration, not a real vendor adjudication.

The terms `trust`, `Trustworthy vendor`, and `trustworthy-versus-risky` still
sound more conclusive than the implemented decision boundary. A separate
follow-on records this copy-level safety improvement without changing scores.

### 5. Recommendation and evidence

The live Subaru report made the main safety distinctions visible:

- risk score 43 / moderate;
- recommendation `complete diligence`;
- 2 of 7 categories covered and 29% completeness;
- current ownership and sanctions-screen evidence;
- missing financial, legal, cyber, adverse-media, and supply-criticality
  coverage;
- recommendation separate from analyst disposition; and
- explicit statement that missing, staged, rejected, and simulated evidence did
  not contribute.

The report still displayed a narrative sole-source indicator while the
supply-criticality category said its claimless evidence was excluded. That
cross-surface contradiction is already covered by Task #86 (Prevent unsupported
clear results and recommendations), so it was not duplicated.

Following `Review claims` loaded seven committed Subaru claims scoped to the V-22
program. The records exposed assertion, truth state, source, method, confidence,
evidence kind, and retrieval time. The use of `VERIFIED` for approved claims is
already covered by Task #85 (Stop calling approved evidence automatically
verified), and factor-to-evidence failure behavior is already covered by Task
#84 (Keep decision evidence reachable when requests fail).

## Decision-clarity assessment

| Requirement | Result | Evidence |
| --- | --- | --- |
| Mission impact | **Fail at guided graph** | No plain-language readiness consequence or affected supplier was returned. Covered by Task #60. |
| Supplier criticality | **Partial** | A sole-source narrative appeared later in the report, but supply criticality remained an explicit evidence gap. |
| Sole-source / concentration | **Partial** | Presets and indicators were visible; the guided result did not explain supported fact versus unknown alternative. |
| Confidence | **Pass** | Visible separately in portfolio, comparison, report factors, and claims. |
| Completeness | **Pass** | 29% and five missing categories were prominent; gaps were not treated as clear. |
| Freshness | **Partial** | Profile freshness was clear; mission-level live freshness was unknown without a concise data-mode explanation. |
| Simulation | **Pass** | Page, profile, and evidence-level labels were conspicuous and used allegation-safe language. |
| Recommended action | **Pass after report** | `complete diligence` and the separate human disposition were understandable. |
| Decision-support boundary | **Pass with copy concern** | No automatic award, eligibility, or disqualification action occurred; some “trustworthy” language remains overly conclusive. |

## Comprehension answers

- **Does a high score mean the vendor must be excluded?** No. It prioritizes
  review and remains separate from the human disposition.
- **Does missing alternate-source data prove sole source?** No. The unsupported
  supply-criticality input was excluded and shown as a gap.
- **Can simulated evidence be briefed as a real allegation?** No. The comparison
  and graph made the simulation boundary conspicuous.
- **What should happen next?** Complete diligence on the affected vendor and
  assign a human review action; do not make an award decision from the score.
- **What fact is still needed before an acquisition decision?** Reviewable
  evidence for the sole-source/alternate-source and component-criticality claim,
  plus the five uncovered risk categories.

## Follow-on coverage

Existing work, not duplicated:

- Task #60 — Simplify Graph Workspace
- Task #84 — Keep decision evidence reachable when requests fail
- Task #85 — Stop calling approved evidence automatically verified
- Task #86 — Prevent unsupported clear results and recommendations
- Task #100 — Back every sole-source risk score with reviewable evidence

New follow-ons from this review:

- Task #129 — Make rehearsal data unmistakable before acquisition decisions
- Task #130 — Keep vendor labels from sounding like procurement clearance

## Evidence

- `docs/reviews/acquisition-decision-evidence/journey.json`
- `docs/reviews/acquisition-decision-evidence/01-mission-entry.jpg`
- `docs/reviews/acquisition-decision-evidence/02-supply-exposure.jpg`
- `docs/reviews/acquisition-decision-evidence/03-portfolio.jpg`
- `docs/reviews/acquisition-decision-evidence/04-comparison.jpg`
- `docs/reviews/acquisition-decision-evidence/05-recommendation.jpg`
- `docs/reviews/acquisition-decision-evidence/06-claims-loaded.jpg`