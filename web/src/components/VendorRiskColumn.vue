<template>
  <section class="vendor-column" :aria-label="`${profile.name} risk profile`">
    <template v-if="!category">
      <header class="vendor-head">
        <div>
          <div class="d-flex align-center flex-wrap ga-1">
            <h2 class="text-h6">{{ profile.name }}</h2>
            <v-chip v-if="profile.simulated" size="x-small" color="warning" variant="flat">SIMULATED</v-chip>
            <v-chip size="x-small" variant="tonal">{{ profile.sourceMode === 'frozen' ? 'FROZEN PRESET' : 'LIVE REPORT' }}</v-chip>
          </div>
          <div class="text-caption">Framework {{ profile.contract_version }}</div>
        </div>
        <div class="score" :class="bandClass(profile.band)">
          <strong>{{ profile.score == null ? '—' : profile.score }}</strong>
          <span>{{ label(profile.band) }}</span>
        </div>
      </header>

      <v-alert v-if="profile.score == null" type="warning" variant="tonal" density="compact" class="mt-3">
        Not assessed. Missing evidence is not a zero-risk result.
      </v-alert>

      <dl class="metrics">
        <div><dt>Confidence</dt><dd>{{ percent(profile.confidence) }}</dd></div>
        <div><dt>Completeness</dt><dd>{{ percent(profile.completeness) }}</dd></div>
        <div><dt>Freshness</dt><dd><TruthBadge :value="profile.freshness" /></dd></div>
        <div><dt>Disposition</dt><dd>{{ label(profile.disposition) }}</dd></div>
      </dl>

      <div class="gaps">
        <h3 class="text-subtitle-2 mb-1">Gaps & required actions</h3>
        <v-alert v-if="!profile.diligence_flags.length" type="success" variant="tonal" density="compact">No diligence gaps in this profile.</v-alert>
        <v-alert v-for="gap in profile.diligence_flags" :key="`${gap.category}-${gap.code}`" type="warning" variant="tonal" density="compact" class="mb-1">
          <b>{{ label(gap.code) }}</b><br>{{ gap.message }}
          <div v-if="gap.excluded_truth_statuses?.length" class="d-flex flex-wrap align-center ga-1 mt-1">
            <span>Excluded:</span><TruthBadge v-for="status in gap.excluded_truth_statuses" :key="status" :value="status" />
          </div>
          <div v-for="evidence in gap.excluded_evidence || []" :key="evidence.evidence_ref || evidence.id" class="excluded-evidence">
            <TruthBadge :value="evidence.truth_status || evidence.status || 'unknown'" />
            <v-chip v-if="evidence.simulated" size="x-small" color="warning" variant="flat">SIMULATED</v-chip>
            <span>{{ evidence.evidence_ref || evidence.id || 'Unresolved evidence' }}</span>
          </div>
        </v-alert>
      </div>
    </template>

    <article v-else class="category-row">
      <div class="category-summary">
        <div>
          <strong>{{ row.label || label(row.id) }}</strong>
          <span class="text-caption d-block">Weight {{ row.weight }} · {{ label(row.severity || 'unavailable') }}</span>
        </div>
        <div class="contribution" :class="{ active: row.contribution > 0 }">
          {{ row.contribution > 0 ? '+' : '' }}{{ row.contribution }}
        </div>
      </div>
      <div class="d-flex flex-wrap ga-1 mt-1">
        <TruthBadge :value="row.freshness" />
        <v-chip size="x-small" variant="outlined">confidence {{ percent(row.confidence) }}</v-chip>
        <v-chip v-if="!row.factors.length" size="x-small" color="warning" variant="tonal">NO APPROVED EVIDENCE</v-chip>
      </div>
      <v-expansion-panels v-if="nonzeroFactors.length" variant="accordion" class="mt-2">
        <v-expansion-panel v-for="factor in nonzeroFactors" :key="factor.rule_id">
          <v-expansion-panel-title>
            <span>{{ factor.label || label(factor.rule_id) }}</span>
            <v-chip size="x-small" color="error" variant="tonal" class="ml-2">+{{ factor.contribution }}</v-chip>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <p class="text-body-2 mb-2"><b>Rule {{ factor.rule_id }}:</b> {{ factor.explanation || 'Contribution determined by the published risk contract.' }}</p>
            <div class="d-flex flex-wrap ga-1 mb-2">
              <TruthBadge value="derived" />
              <TruthBadge v-if="factor.freshness" :value="factor.freshness" />
            </div>
            <div v-if="factor.evidence?.length">
              <div v-for="e in factor.evidence" :key="e.id || e.claim_id" class="evidence">
                <div class="d-flex flex-wrap ga-1">
                  <TruthBadge :value="e.truth_status || e.status || 'unknown'" />
                  <v-chip v-if="e.simulated" size="x-small" color="warning" variant="flat">SIMULATED</v-chip>
                </div>
                <b>{{ e.source || 'Source unavailable' }}</b>
                <div>{{ e.detail || 'No evidence detail provided.' }}</div>
                <small>{{ e.retrieved_at ? `Retrieved ${e.retrieved_at}` : 'Retrieval date unavailable' }}<span v-if="e.confidence != null"> · confidence {{ percent(e.confidence) }}</span></small>
              </div>
            </div>
            <div v-else-if="factor.provenance" class="evidence">
              <TruthBadge value="verified" />
              <b class="d-block">{{ factor.provenance.source || 'Graph evidence' }}</b>
              <div>Evidence references: {{ factor.evidence_refs.join(', ') || 'unavailable' }}</div>
              <small>{{ factor.provenance.retrieved_at ? `Retrieved ${factor.provenance.retrieved_at}` : 'Retrieval date unavailable' }}<span v-if="factor.provenance.confidence != null"> · confidence {{ percent(factor.provenance.confidence) }}</span></small>
            </div>
            <p v-else class="text-body-2 text-warning">Evidence references: {{ factor.evidence_refs.join(', ') || 'unavailable' }}</p>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RiskCategory, VendorRiskProfile } from '../api/client'
import TruthBadge from './TruthBadge.vue'

const props = defineProps<{
  profile: VendorRiskProfile
  category?: { id: string; label?: string; weight: number }
}>()
const row = computed<RiskCategory>(() => props.profile.categories.find(item => item.id === props.category?.id) || {
  id: props.category?.id || 'unavailable',
  label: props.category?.label,
  weight: props.category?.weight || 0,
  severity: null,
  contribution: 0,
  confidence: 0,
  freshness: 'missing',
  factors: [],
})
const nonzeroFactors = computed(() => row.value.factors.filter(factor => (factor.contribution || 0) > 0))
const label = (value: string) => value.replaceAll(/[._-]/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
const percent = (value: number) => `${Math.round(value * 100)}%`
const bandClass = (band: string) => `band-${band}`
</script>

<style scoped>
.vendor-column { min-width: 0; height: 100%; }
.vendor-head { min-height: 92px; display: flex; justify-content: space-between; align-items: start; gap: 16px; border-bottom: 1px solid rgba(128,128,128,.25); padding-bottom: 12px; }
.score { min-width: 76px; border-radius: 8px; padding: 7px 10px; text-align: center; background: rgba(128,128,128,.12); }
.score strong { display: block; font-size: 24px; line-height: 1; }.score span { font-size: 10px; text-transform: uppercase; }
.band-low { color: #2e7d32; }.band-moderate { color: #ed6c02; }.band-high,.band-critical { color: #d32f2f; }
.metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 14px 0; }
.metrics div { background: rgba(128,128,128,.08); padding: 7px 9px; border-radius: 6px; }.metrics dt { font-size: 10px; opacity: .65; text-transform: uppercase; }.metrics dd { margin: 2px 0 0; font-size: 13px; font-weight: 600; }
.category-row { height: 100%; padding: 12px 0; border-top: 1px solid rgba(128,128,128,.2); }
.category-summary { display: flex; justify-content: space-between; gap: 8px; }.contribution { font: 700 17px ui-monospace, monospace; opacity: .55; }.contribution.active { color: #d32f2f; opacity: 1; }
.evidence { border-left: 3px solid rgba(128,128,128,.3); padding: 6px 9px; margin-top: 7px; font-size: 12px; }.evidence small { opacity: .7; }
.excluded-evidence { display: flex; gap: 5px; align-items: center; margin-top: 5px; font-size: 11px; }
</style>