# Vendor Risk Journey Review

**Review date:** 2026-09-08  
**Build:** `7e25eba` on `replit-configuration`  
**Mode:** Replit development workflow with the deterministic `uc7-fixtures-v1` seed  
**Mission scope:** V-22 Osprey Program (PMA-275), `ent_6484d4d13b76`

## Persona and decision boundary

This review adopted the counterintelligence/vendor-risk analyst persona in
`docs/NDIA_USER_PERSONAS.md`. The analyst needed to prioritize two vendors under
one UC-11 framework, challenge weak or incomplete evidence, inspect ownership
and screening lineage, and record a proportionate human action.

The evidence threshold used throughout the review was:

- a score is a prioritization rule, not a probability of compromise;
- confidence is assertion strength, completeness is coverage, and freshness is
  retrieval currency;
- a negative screen is source- and method-specific, not proof of safety;
- staged, rejected, conflicting/disputed, or simulated information cannot drive
  a verified finding;
- recommendations remain advisory and separate from both claim truth and human
  disposition.

No private, classified, export-controlled, or procurement-sensitive data was
used, and no real vendor was adjudicated or disqualified.

## Scenario outcome

### 1. Portfolio triage

The portfolio loaded 65 program vendors and supported ranking and filtering by
risk, category, confidence, completeness, freshness, tier, and simulation.
Loading rows were labeled `ASSESSING` rather than being presented as zero risk.

The highest live profile was SUBARU CORPORATION:

| Measure | Reviewed value |
| --- | --- |
| Overall score / band | 50 / high |
| Deterministic recommendation | Escalate for review |
| Confidence | 92% |
| Completeness | 43% (3 of 7 categories) |
| Freshness | Diligence required |
| Material contributions | Ownership +15; supply criticality +10 |
| Missing categories | Financial, legal, cyber, adverse media |

The screen did not collapse these values into one conclusion. In particular,
the 43% completeness and four missing-category flags remained prominent beside
the high score and recommendation.

### 2. Risky-versus-lower-risk comparison

The live comparison used SUBARU CORPORATION and UNITED PARCEL SERVICE INC under
`uc11.vendor-risk.v1`.

| Measure | SUBARU CORPORATION | UNITED PARCEL SERVICE INC |
| --- | --- | --- |
| Score / band | 50 / high | 0 / low |
| Confidence | 92% | 92% |
| Completeness | 43% | 43% |
| Freshness | Diligence required | Diligence required |
| Recommendation | Escalate for review | Complete diligence |

This was a useful comprehension check: the lower-risk vendor was not presented
as fully trustworthy or cleared. Its zero score remained paired with 43%
completeness, diligence-required freshness, and explicit missing categories.
The frozen judged preset also remained unmistakably simulated on both sides.

The comparison itself is not identity-safe for normal analysts: it requires
internal entity IDs and does not provide a searchable comparator selector.
Task #101 (Let analysts choose the right vendor for comparison) captures this
distinct improvement.

### 3. Entity, claims, artifacts, and evidence trace

#### Ownership/control factor

The Subaru ownership factor was traceable in the API contract as follows:

- deterministic rule: `ownership.foreign-parent.v1`;
- contribution: +15, high severity;
- explanation: ultimate parent jurisdiction is JP;
- graph relationship: `rel_89e5f1054c4d`;
- current claim: `clm_8f9d556959c9`, committed;
- source/method: GLEIF connector;
- retrieved: 2026-09-08T15:04:07Z;
- confidence: 85.5%.

The risk card clearly separated the derived rule from its verified claim. The
claims page exposed the assertion, method, trust, confidence, retrieval time,
and registry artifact. Exact factor-to-evidence navigation and failure recovery
are already covered by Task #84 (Keep decision evidence reachable when requests
fail).

#### Negative sanctions and exclusion screens

The two clear screening factors were bounded to their actual retrievals:

- SAM exclusions: no active exclusion matched by UEI/CAGE/name against the
  identified public extract;
- OFAC: no match against 19,329 SDN entries.

Both records retained committed claim status, named source, connector method,
95% confidence, retrieval time, and a source artifact. The interface therefore
supported the statement “these named screens produced no match at this time,”
not “the vendor is safe or eligible.” Broader narrative alignment for clear,
unknown, stale, and disputed evidence is already covered by Task #86 (Prevent
unsupported clear results and recommendations).

#### Supply-criticality factor

The Subaru supply-criticality factor exposed:

- deterministic rule: `supply.sole-source.v1`;
- contribution: +10, medium severity;
- graph relationship: `rel_19a0fb510796`;
- source/method: USAspending connector;
- retrieved: 2026-09-08T15:04:02Z;
- confidence: 95%.

This trace failed the full evidence threshold. The scored relationship had no
backing claim, no claim status, and no exact award artifact in the factor
contract. Source metadata alone does not allow an analyst to review or
challenge the material sole-source assertion end to end. Task #100 (Back every
sole-source risk score with reviewable evidence) captures this high-severity
lineage defect.

### 4. Truth-state and false-positive probes

| State or condition | Result |
| --- | --- |
| Staged | Visible and actionable only in the staged claims queue |
| Committed | Rendered as verified while retaining source lineage |
| Rejected | Preserved in a separate queue and excluded from approved scoring |
| Conflicting/disputed | Represented separately from committed truth in ownership records |
| Derived | Risk factors identify their deterministic rule separately from evidence |
| Simulated | Contagious across the scenario vendor, findings, excluded evidence, and decision |
| Missing | Rendered as “No approved, non-simulated evidence,” never as clear |
| Stale | Produces a diligence flag rather than silently appearing current |
| No hit | Describes the named source, method, retrieved extract, and match result |

One same-name identity hazard was also reproduced: two RAYTHEON COMPANY rows had
different UEIs while sharing the same LEI and ticker. The portfolio did not show
those differentiators, making selection ambiguous. Task #101 includes explicit
identity cues and ambiguity handling without silently merging records.

### 5. Human decision boundary

A scenario-only disposition was recorded for Ningbo Precision Castings Ltd
(simulated):

- action: Investigate;
- scope: ownership evidence gap;
- owner: Vendor Risk Review;
- due date: 2026-09-15;
- rationale: verify ownership identity and obtain approved non-simulated
  evidence before relying on a risk conclusion.

The resulting event was append-only, attributable to the local actor, scoped to
the V-22 program, versioned, and visibly simulated. The interface continued to
show the deterministic recommendation separately and stated that the human
action did not alter scoring, claim truth, eligibility, or award decisions.

## Safety conclusion

The journey supports a defensible review queue without making an intelligence,
eligibility, or award determination. Subaru should enter enhanced review before
UPS because its approved ownership and supply-criticality rules contribute
material risk, but the recommendation remains provisional: four categories are
uncovered, negative screens are source-specific, and the sole-source factor
needs a complete claim-and-artifact chain.

## Follow-on coverage

New tasks created by this review:

- Task #100 — Back every sole-source risk score with reviewable evidence
- Task #101 — Let analysts choose the right vendor for comparison

Relevant existing tasks, not duplicated:

- Task #84 — Keep decision evidence reachable when requests fail
- Task #86 — Prevent unsupported clear results and recommendations

## Review evidence

- `review-evidence/vendor-risk-portfolio.jpg`
- `review-evidence/live-subaru-ups-comparison.jpg`
- `review-evidence/vendor-risk-comparison-preset.jpg`
- `review-evidence/subaru-risk-report.jpg`
- `review-evidence/subaru-claims.jpg`
- `review-evidence/subaru-artifacts.jpg`
- `review-evidence/simulated-analyst-decision.jpg`