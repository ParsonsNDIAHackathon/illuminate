# Illuminate architecture and lineage brief

## Judge view: evidence in, reviewable decision support out

Illuminate fuses public supplier data into an evidence-backed graph. Its central design rule is that a source statement is not automatically treated as a fact, and a graph signal is not automatically treated as a decision.

```text
PUBLIC SOURCE
  USAspending / GLEIF / SEC EDGAR / LittleSis / SAM / OFAC / UN Security Council
        │  retrieve + retain source identity, URL, time, method, quality
        ▼
ARTIFACT ──EVIDENCES──► CLAIM (staged / committed / rejected)
                              │
                  trust rule or human review
                              ▼
GRAPH FACT
  supplier, ownership, geography, person, category, screening observation
                              │
                    deterministic graph analytics
                              ▼
DERIVED FINDING
  typed path + contributing claims + truth/simulation status
                              │
                   versioned, explainable scoring rules
                              ▼
SCORE ──► RECOMMENDATION ──► VERSIONED EXPORT ──► CATALOG METADATA
          decision support      machine contract      discovery record
          (not adjudication)    for consumers         describing the export
```

The first three stages are implemented in the current graph and claim pipeline. Derived findings, explainable scoring, versioned exports, and catalog publication are explicit downstream contracts being completed in parallel. The architecture preserves the lineage needed by those contracts; this brief does not imply that unfinished endpoints are available.

## The narrative in plain language

1. **Collect.** A connector retrieves a public record. The source's coverage determines what the record can support; absence of a record is not proof of safety.
2. **Preserve evidence.** The record becomes an `Artifact`, not an unbounded raw blob. Its source URL and retrieval context remain available.
3. **Stage the assertion.** Every proposed fact becomes a `Claim` with subject, predicate, object or value, source, method, confidence, retrieval time, and lifecycle status.
4. **Apply trust.** An authoritative connector may auto-commit a sufficiently confident claim. Open-source claims remain staged until a human approves them or two independent sources corroborate them. Rejected claims remain distinguishable from committed truth.
5. **Materialize the graph fact.** A committed claim writes the direct relationship or property used for fast traversal. That fact carries `claim_id`, so a user can traverse back to the claim and its artifact.
6. **Derive, do not invent.** Analytics traverse committed graph facts to identify patterns such as sole-source paths, foreign-parent paths, shared people, or screening observations. A finding should retain its typed path and contributing claim IDs.
7. **Score deterministically.** Risk families, weights, thresholds, rule-set version, and data completeness belong in the score output. Optional AI may summarize the structured result, but must not create evidence, alter the score, or silently promote a claim.
8. **Recommend for review.** Recommendations are explainable decision support—investigate, monitor, seek an alternate source—not autonomous eligibility or award decisions.
9. **Publish safely.** A versioned export is the machine-readable data product. Catalog metadata describes that product, its owner, update cadence, usage constraints, quality, schema version, and access path; it does not duplicate the graph or evidence.

## Trust boundaries and control points

| Boundary | What crosses it | Control |
|---|---|---|
| External source → connector | Public records and source errors | Source-specific parsing; source identity, method, retrieval time, and evidence retained |
| Connector → claim store | Proposed assertion | Always staged first; status is explicit |
| Claim → graph fact | Approved assertion | Authoritative confidence rule, independent corroboration, or human review |
| Graph → analytics | Committed facts and explicitly marked simulation | Deterministic traversal; typed paths and claim references |
| Analytics → score | Structured findings | Versioned rules and weights; completeness and contributing evidence exposed |
| Score → optional AI | Structured, bounded result | AI explains or summarizes only; it is not the source of truth |
| User/agent → graph write | Validated Cypher request | Allowlist, read/write classification, rolled-back impact preview, explicit approval |
| Export → downstream consumer | Safe, versioned records | Schema validation, stable identifiers, simulation/truth status, no credentials or restricted raw payloads |

### Human review

- Open-source assertions that lack independent corroboration stay `staged`.
- Reviewers can commit or reject a claim; the lifecycle is not erased.
- A graph interlock or fuzzy entity match is a lead, not an accusation. Resolution method and confidence remain visible.
- Write requests are previewed in a rolled-back transaction and held for approval. Destructive requests require explicit acknowledgement and are never silently approved.

### Simulation

The demo may add one adversarial scenario to exercise the full path. Synthetic nodes and relationships carry `simulated: true` and are visually badged. Derived records must propagate simulation status. Simulated evidence must never be presented as observed source coverage or mixed into real-world findings without a visible label.

### Optional AI

Illuminate still supports graph browsing and named template questions without a model key. When enabled, AI can select tools, propose validated Cypher, and summarize returned evidence. It cannot bypass the Cypher validator or write permission gate; credentials stay server-side and are not included in prompts. Deterministic rules—not model prose—produce risk scores.

## Deployment portability

| Replit development path | Preserved Docker path |
|---|---|
| `scripts/replit-dev.sh` starts Neo4j, FastAPI, and the Vue development server in one workflow. | `make up` uses `docker-compose.yml` to start restore, Neo4j 5 + APOC, the API, and the built web server. |
| Neo4j uses project-writable data, log, transaction, configuration, and plugin directories. | Neo4j data uses a named volume; API settings use the mounted `api/data` directory. |
| Services bind to `0.0.0.0`; the web workflow uses Replit's preview port and the frontend uses same-origin API routing. | Local ports are web `8080`, API `8000`, Neo4j HTTP `7474`, and Bolt `7687`. |
| Intended for rapid development and demonstration. | Intended as a portable, reproducible deployment path with health ordering plus backup/restore tooling. |

These paths demonstrate portability, not production accreditation. The checked-in defaults are development settings. Neither path by itself establishes an ATO, CMMC level, FedRAMP authorization, classified-data approval, production availability target, or operational security posture.

## Presenter notes: likely judge questions

**How can I trace an answer to its source?**  
Start at the finding's typed graph path, follow each graph fact's `claim_id` to the committed claim, then follow `EVIDENCES` to the artifact and source URL. The executed query is shown for interactive graph answers. The export contract is intended to carry the same path and provenance without requiring the Illuminate UI.

**Why not write connector results straight into the graph?**  
Because source statements have different authority and can conflict. Reified claims preserve who said what, when, by what method, and with what confidence. The direct graph edge is only a query-speed projection of a committed claim.

**How is the score calibrated?**  
The score is a transparent prioritization rule, not a probability of compromise. Calibration should publish the rule-set version, weights, thresholds, completeness, and validation set; compare results with analyst outcomes; test sensitivity and false-positive rates; and change weights only through versioned review. No claim of operational calibration should be made until that evaluation is complete.

**What does “no hit” mean?**  
Only that the named source, retrieved at the recorded time, produced no match under the recorded method. It does not mean the entity is safe, currently eligible, or absent from sources not queried.

**What source coverage is supported?**  
The current demo contains cached public records from the sources enumerated in `details.html`. Coverage varies by connector, identity resolution, quota, reporting lag, and jurisdiction. The system does not claim complete supplier tiers, beneficial ownership, adverse media, sanctions, or debarment coverage.

**Where can AI make a mistake?**  
It can misunderstand a question, choose an imperfect tool, generate a query that is rejected, or produce an imprecise summary. The mitigation is bounded tools, validated Cypher, visible executed queries, evidence-linked outputs, and deterministic scoring. AI output should be reviewed and is not evidence.

**How are fuzzy matches handled?**  
Stable identifiers are preferred. Name-based resolution records its method and confidence, and low-confidence candidates are not silently merged. A match is explainable and reviewable rather than hidden inside ingestion.

**How is interoperability achieved?**  
The graph is the working model; the versioned finding export is the consumer contract. Stable IDs, typed paths, provenance, truth and simulation status, classification, licensing/usage notes, quality, pagination, and watermarks allow consumers to integrate without depending on the Vue UI or Neo4j serialization. MCP exposes the same bounded tool contract used by in-app chat.

**What are the main security controls today?**  
Server-side encrypted connector keys, no keys in model prompts, schema and procedure allowlists, query classification, bounded reads, and preview-plus-approval for writes. Public-source provenance is retained rather than laundered into unattributed assertions.

**What remains for production hardening?**  
Replace development credentials; integrate enterprise identity and role-based access; use managed secrets and key rotation; enforce network segmentation and TLS; add immutable audit logs, retention policy, malware/content handling, egress controls, rate limits, monitoring, disaster-recovery tests, dependency and image scanning, privacy/classification review, source-license review, model governance, red-team testing, and an authorization process appropriate to the operating environment.

**What are the sustainable extension points?**  
Add connectors through the same artifact-and-claim boundary; add analytics as deterministic finding producers; evolve scores with versioned rules; add consumers through the export schema or MCP; and publish discovery metadata without coupling the catalog to Neo4j. Each extension preserves lifecycle, provenance, and simulation semantics.

## Safe closing statement

> Illuminate is an evidence-backed decision-support prototype. It demonstrates traceable public-source fusion, reviewable graph analytics, deterministic scoring boundaries, and portable interfaces. It does not claim exhaustive coverage, adjudicative authority, operational calibration, or security accreditation.