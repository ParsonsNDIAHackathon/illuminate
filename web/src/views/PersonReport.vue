<template>
  <!-- The person's page. A person is never a finding on their own account in this graph —
       they matter through where they sit — so the roles come first and every role carries the
       standing of the organisation at the other end: flagged, scored, a supplier or not. -->
  <v-container fluid v-if="rep" class="report">
    <div class="d-flex align-center ga-2 mb-1">
      <v-btn icon="mdi-arrow-left" variant="text" @click="router.back()" />
      <h2 class="text-h6">{{ rep.identity.name }}</h2>
      <v-chip v-if="rep.identity.flagged" size="x-small" color="error" variant="tonal" :title="rep.identity.flag_reason">flagged</v-chip>
      <v-chip v-if="rep.identity.simulated" size="x-small" color="warning" variant="tonal">SIM</v-chip>
      <v-chip v-if="rep.identity.public_official" size="x-small" color="secondary" variant="tonal">Public official</v-chip>
      <v-chip v-if="rep.risk?.score != null" size="x-small" variant="tonal" :color="bandChip(rep.risk.band)"
              :title="rep.risk.note" @click="tab = 'risk'" style="cursor:pointer">
        risk {{ rep.risk.score }} · {{ bandLabel(rep.risk.band) }}<span v-if="isThin(rep.risk.confidence)"> ?</span>
      </v-chip>
      <v-spacer />
      <v-btn prepend-icon="mdi-graph" @click="openInGraph">Open in graph</v-btn>
    </div>
    <div class="text-caption mb-3" style="opacity:.75">
      {{ rep.current.length }} current {{ rep.current.length === 1 ? 'seat' : 'seats' }} · {{ rep.former.length }} former · {{ entityCount }} {{ entityCount === 1 ? 'organisation' : 'organisations' }}
      <span v-if="rep.risk?.top_factor"> · {{ rep.risk.top_factor }}</span>
    </div>
    <v-tabs v-model="tab" density="compact"><v-tab value="roles">Roles</v-tab><v-tab value="risk">Risk</v-tab><v-tab value="artifacts">Artifacts</v-tab></v-tabs>
    <v-window v-model="tab" class="mt-3">
      <v-window-item value="roles">
        <v-row>
          <v-col cols="12" md="8">
            <p class="text-caption mb-2" style="opacity:.7">One edge per tenure. The chips describe the organisation at the other end, which is where the exposure lives.</p>
            <v-list density="compact" lines="two">
              <v-list-subheader>Current</v-list-subheader>
              <v-list-item v-for="r in rep.current" :key="r.edge_id" :subtitle="tenure(r)">
                <template #title><router-link :to="`/entities/${r.entity_id}`">{{ r.entity }}</router-link> — {{ r.title || r.role_type || 'role' }}</template>
                <template #append>
                  <v-chip v-if="r.flagged" size="x-small" color="error" variant="tonal" :title="r.flag_reason">Flagged</v-chip>
                  <v-chip v-if="r.risk_score != null" size="x-small" variant="tonal" :color="bandChip(r.risk_band)" class="ml-1">{{ scoreLabel(r.risk_score, r.risk_band) }}</v-chip>
                  <v-chip v-if="r.supplier" size="x-small" color="secondary" variant="tonal" class="ml-1">Supplier</v-chip>
                  <v-chip v-if="r.simulated" size="x-small" color="warning" variant="tonal" class="ml-1">SIM</v-chip>
                  <a v-if="r.source_url" :href="r.source_url" target="_blank" rel="noopener" class="ml-2 text-caption">{{ r.source }}</a>
                </template>
              </v-list-item>
              <v-list-item v-if="!rep.current.length" subtitle="No current seat on record." />
              <v-list-subheader>Former</v-list-subheader>
              <v-list-item v-for="r in rep.former" :key="r.edge_id" :subtitle="tenure(r)">
                <template #title><router-link :to="`/entities/${r.entity_id}`">{{ r.entity }}</router-link> — {{ r.title || r.role_type || 'role' }}</template>
                <template #append>
                  <v-chip v-if="r.flagged" size="x-small" color="error" variant="tonal" :title="r.flag_reason">Flagged</v-chip>
                  <v-chip v-if="r.risk_score != null" size="x-small" variant="tonal" :color="bandChip(r.risk_band)" class="ml-1">{{ scoreLabel(r.risk_score, r.risk_band) }}</v-chip>
                  <a v-if="r.source_url" :href="r.source_url" target="_blank" rel="noopener" class="ml-2 text-caption">{{ r.source }}</a>
                </template>
              </v-list-item>
              <v-list-item v-if="!rep.former.length" subtitle="No former seat on record." />
            </v-list>
          </v-col>
          <v-col cols="12" md="4">
            <v-card variant="outlined" class="mb-3"><v-card-text>
              <span class="section">Screens</span>
              <div class="d-flex flex-wrap ga-1 mt-1">
                <v-chip v-for="s in rep.screens" :key="s.predicate" size="small" variant="tonal" :color="s.result === 'hit' ? 'error' : s.result === 'clear' ? 'success' : undefined" :title="s.detail">{{ s.source }} {{ s.result }}</v-chip>
                <span v-if="!rep.screens.length" class="text-body-2" style="opacity:.6">Not yet screened.</span>
              </div>
            </v-card-text></v-card>
            <v-card variant="outlined" class="mb-3"><v-card-text>
              <span class="section">Provenance</span>
              <dl>
                <dt>Source</dt><dd>{{ rep.identity.source || '—' }} <a v-if="rep.identity.source_url" :href="rep.identity.source_url" target="_blank" rel="noopener">↗</a></dd>
                <dt>Retrieved</dt><dd>{{ (rep.identity.retrieved_at || '').slice(0, 10) || '—' }}</dd>
                <dt>Method</dt><dd>{{ rep.identity.method || '—' }}<span v-if="rep.identity.confidence != null"> · confidence {{ rep.identity.confidence }}</span></dd>
                <template v-if="rep.identity.person_types?.length"><dt>Types</dt><dd>{{ rep.identity.person_types.join(', ') }}</dd></template>
              </dl>
            </v-card-text></v-card>
            <v-card variant="outlined"><v-card-text><span class="section">Sources</span><p class="text-body-2">{{ rep.sources.join(' · ') || '—' }}</p></v-card-text></v-card>
          </v-col>
        </v-row>
      </v-window-item>
      <v-window-item value="risk">
        <template v-if="rep.risk && rep.risk.score != null">
          <div class="d-flex align-center ga-3 mb-2">
            <v-chip size="large" variant="tonal" :color="bandChip(rep.risk.band)">{{ rep.risk.score }}/100 · {{ bandLabel(rep.risk.band) }}</v-chip>
            <div>
              <div class="text-body-2">{{ rep.risk.top_factor || 'No dimension graded above clear' }}</div>
              <div class="text-caption" :class="{ 'text-warning': isThin(rep.risk.confidence) }">
                {{ confidenceNote(rep.risk.confidence, rep.risk.dimensions_scored, rep.risk.dimensions_requested) }}
              </div>
            </div>
          </div>
          <v-list density="compact" lines="two">
            <v-list-item v-for="c in rep.risk.components" :key="c.dimension" :title="c.label" :subtitle="c.detail || ''">
              <template #prepend><v-icon :icon="sevIcon(c.severity)" :color="sevColor(c.severity)" /></template>
              <template #append>
                <span v-if="c.weight" class="text-caption mr-2" style="opacity:.55" title="Relative weight among the dimensions that returned data">×{{ c.weight }}</span>
                <v-chip size="x-small" variant="tonal" :color="sevColor(c.severity)">{{ c.severity ? c.severity : 'No data' }}</v-chip>
                <a v-if="c.source_url" :href="c.source_url" target="_blank" rel="noopener" class="ml-2 text-caption">{{ c.source }}</a>
                <span v-else class="ml-2 text-caption" style="opacity:.7">{{ c.source || '—' }}</span>
              </template>
            </v-list-item>
          </v-list>
          <v-alert v-if="rep.risk.note" variant="tonal" density="compact" class="mt-2" type="info">{{ rep.risk.note }}</v-alert>
          <p class="text-caption mt-1" style="opacity:.6" v-if="rep.risk.reference">{{ rep.risk.reference }}</p>
        </template>
        <p v-else class="text-body-2" style="opacity:.6">Nothing to grade yet — no dimension returned data for this person.</p>
      </v-window-item>
      <v-window-item value="artifacts">
        <v-table density="compact"><thead><tr><th>Kind</th><th>Title</th><th>Source</th><th>Date</th><th>View</th></tr></thead>
          <tbody><tr v-for="a in rep.artifacts" :key="a.id"><td>{{ a.kind }}</td><td><SourceLink :href="a.url" :artifact-id="a.id">{{ a.title }}</SourceLink></td><td>{{ a.source }}</td><td>{{ a.published_at || (a.retrieved_at || '').slice(0, 10) }}</td><td><v-btn icon="mdi-text-box-search-outline" size="x-small" variant="text" title="View contents" @click="rawId = a.id" /></td></tr></tbody></v-table>
        <ArtifactViewer :artifact-id="rawId" @close="rawId = null" />
        <p v-if="!rep.artifacts.length" class="text-body-2 mt-2" style="opacity:.6">No artifacts attached to this person.</p>
      </v-window-item>
    </v-window>
  </v-container>
  <v-container v-else-if="error">
    <p class="text-body-2 text-error">{{ error }}</p>
    <v-btn variant="tonal" to="/people">Back to people</v-btn>
  </v-container>
  <v-container v-else><v-progress-linear indeterminate /></v-container>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import ArtifactViewer from '../components/ArtifactViewer.vue'
import SourceLink from '../components/SourceLink.vue'
import { bandChip, bandLabel, confidenceNote, isThin, scoreLabel, sevColor, sevIcon } from '../styles/risk'
import { useOpenOnCanvas } from '../composables/openOnCanvas'
const props = defineProps<{ id: string }>()
const router = useRouter(); const { openOnCanvas } = useOpenOnCanvas()
const rep = ref<any>(null); const tab = ref('roles'); const rawId = ref<string | null>(null); const error = ref('')
const entityCount = computed(() => new Set((rep.value?.roles || []).map((r: any) => r.entity_id)).size)
function tenure(r: any) {
  const span = `${r.from || '?'} – ${r.current ? 'now' : (r.to || '?')}`
  return [r.role_type, span, r.pct ? `${r.pct}%` : null, r.detail].filter(Boolean).join(' · ')
}
async function load() {
  error.value = ''
  try { rep.value = await api.get(`/api/people/${props.id}`) }
  catch (e: any) { rep.value = null; error.value = e?.message || String(e) }
}
function openInGraph() { return openOnCanvas(props.id, 'Person') }
onMounted(load); watch(() => props.id, load)
</script>
<style scoped>
.section { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; opacity: .6; }
dl { display: grid; grid-template-columns: 110px 1fr; gap: 3px 8px; margin: 6px 0 0; font-size: 13px; }
dt { opacity: .6; } dd { margin: 0; }
</style>
