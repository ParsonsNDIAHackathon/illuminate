<template>
  <main class="mission">
    <header class="hero">
      <div>
        <div class="eyebrow">JUDGE-GUIDED MISSION / ACQUISITION DECISION SUPPORT</div>
        <h1>Which vendors can this program trust—and where is the supply chain exposed?</h1>
        <p>Start with a deterministic mission lens, inspect the graph and ranked vendor findings, verify the supporting evidence, then export findings with their review status intact.</p>
        <div class="hero-actions">
          <v-btn color="secondary" size="large" prepend-icon="mdi-radar" :disabled="!missionProgramId" :to="missionProgramId ? presetLink(presets[0]) : undefined">Find supply exposure</v-btn>
          <v-btn size="large" variant="outlined" :disabled="!missionProgramId" :to="missionProgramId ? scopedLink('/portfolio') : undefined">Open vendor triage</v-btn>
        </div>
        <small class="speed">Fast path: the first actionable graph finding is one click away.</small>
      </div>
      <div class="decision-card">
        <span>PROGRAM IN SCOPE</span>
        <v-select v-if="programs.length > 1" v-model="selectedProgramId" :items="programs" item-title="name" item-value="id" label="Mission program" density="compact" hide-details />
        <strong>{{ selectedProgram?.name || 'No program available' }}</strong>
        <small>{{ missionProgramId || programError || 'Add a program in Settings before live graph exploration.' }}</small>
        <v-chip size="small" :color="ready ? 'success' : status === 'loading' ? 'info' : 'warning'" variant="tonal">
          {{ status === 'loading' ? 'Checking readiness' : ready ? 'Mission ready' : 'Operator action needed' }}
        </v-chip>
      </div>
    </header>

    <section aria-labelledby="readiness-title">
      <div class="section-title">
        <div><span>01 / MISSION STATUS</span><h2 id="readiness-title">Know the evidence boundary before deciding.</h2></div>
        <v-btn variant="text" prepend-icon="mdi-refresh" :loading="status === 'loading'" @click="load(true)">Refresh</v-btn>
      </div>
      <div v-if="status === 'loading'" class="state"><v-progress-linear indeterminate color="secondary" /><p>Checking graph, seed coverage, source freshness, and optional services…</p></div>
      <div v-else-if="error" class="state failure">
        <strong>Readiness check unavailable</strong><p>{{ error }}</p>
        <v-btn color="secondary" variant="outlined" @click="load(true)">Retry check</v-btn>
      </div>
      <template v-else-if="health">
        <div v-if="!ready || health.freshness.status !== 'current'" class="advisory">
          <v-icon icon="mdi-alert-outline" /><div><strong>{{ health.message }}</strong> {{ health.required.seed.action || health.freshness.action || 'Live workflow is partially available; frozen judged actions remain usable.' }}</div>
        </div>
        <div class="metrics">
          <article><span>READINESS</span><strong>{{ health.primary_workflow_ready ? 'READY' : 'PARTIAL' }}</strong><small>{{ health.graph_counts.nodes }} nodes · {{ health.graph_counts.relationships }} relationships</small></article>
          <article><span>PROGRAM COVERAGE</span><strong>{{ seedCoverage }}</strong><small>{{ health.required.seed.coverage.status }} seed coverage</small></article>
          <article><span>SOURCE COVERAGE</span><strong>{{ health.source_coverage.length }}</strong><small>{{ sourceRecords.toLocaleString() }} sourced graph records</small></article>
          <article><span>FRESHNESS</span><strong>{{ health.freshness.status.toUpperCase() }}</strong><small>{{ freshnessDetail }}</small></article>
        </div>
        <div class="sources">
          <span v-for="source in health.source_coverage.slice(0, 6)" :key="source.source">{{ source.source }} · {{ source.records.toLocaleString() }}</span>
          <span v-if="!health.source_coverage.length">No source-attributed records reported.</span>
        </div>
      </template>
    </section>

    <section aria-labelledby="actions-title">
      <div class="section-title"><div><span>02 / GUIDED ACTIONS</span><h2 id="actions-title">Choose the question—not the navigation.</h2></div></div>
      <div class="preset-grid">
        <router-link v-for="preset in presets" :key="preset.title" :to="presetLink(preset)" class="preset">
          <v-icon :icon="preset.icon" />
          <div><span>{{ preset.kind }}</span><h3>{{ preset.title }}</h3><p>{{ preset.description }}</p></div>
          <v-icon icon="mdi-arrow-right" />
        </router-link>
      </div>
    </section>

    <section aria-labelledby="workflow-title">
      <div class="section-title"><div><span>03 / DECISION WORKFLOW</span><h2 id="workflow-title">Trace every conclusion to reviewable evidence.</h2></div></div>
      <div class="workflow">
        <router-link :to="scopedLink('/portfolio')"><b>1</b><span><strong>Triage vendors</strong>Rank risk separately from evidence quality.</span></router-link>
        <router-link :to="scopedLink('/compare/vendors')"><b>2</b><span><strong>Compare</strong>Align trustworthy and risky vendor profiles.</span></router-link>
        <router-link to="/claims"><b>3</b><span><strong>Review evidence</strong>Accept or reject staged claims before release.</span></router-link>
        <a href="/api/exports/v1/findings?format=csv"><b>4</b><span><strong>Export with review status</strong>Download the versioned finding contract for controlled downstream review.</span></a>
      </div>
    </section>

    <aside class="simulation">
      <v-icon icon="mdi-flask-outline" /><div><strong>SIMULATION BOUNDARY</strong> Judged presets and any item marked SIM are calibration scenarios—not allegations or verified real-world findings. Live and simulated records remain visibly labeled downstream.</div>
    </aside>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, type ReadinessContract } from '../api/client'
import { useWorkspace } from '../stores/workspace'

const ws = useWorkspace()
const health = ref<ReadinessContract | null>(null)
const status = ref<'loading' | 'done'>('loading')
const error = ref('')
const programError = ref('')
const programs = ref<Array<{ id: string; name: string }>>([])
const selectedProgramId = ref('')
const presets = [
  { kind: 'SUPPLY CHAIN', title: 'Supply exposure', description: 'Reveal dependencies at tier 2 and below, including geographic exposure.', icon: 'mdi-transit-connection-variant', template: 'manufactures_in', params: { country: 'CN', min_tier: 2 } },
  { kind: 'CONTROL', title: 'Hidden control', description: 'Trace suppliers whose ultimate parent is seated outside the United States.', icon: 'mdi-account-lock-outline', template: 'foreign_parent', params: { home_country: 'US' } },
  { kind: 'CONCENTRATION', title: 'Sole source', description: 'Surface suppliers where the program has no represented alternative.', icon: 'mdi-source-branch-remove', template: 'sole_source', params: {} },
  { kind: 'TRIAGE', title: 'Risky vendor', description: 'Open the portfolio ranked by highest assessed risk.', icon: 'mdi-alert-decagram-outline', to: '/portfolio?sort=risk' },
  { kind: 'TRIAGE', title: 'Trustworthy vendor', description: 'Find current, high-confidence vendor profiles for defensible selection.', icon: 'mdi-shield-check-outline', to: '/portfolio?freshness=current&sort=trustworthy' },
  { kind: 'SIDE-BY-SIDE', title: 'Vendor comparison', description: 'Load the frozen judged trustworthy-versus-risky comparison.', icon: 'mdi-compare-horizontal', to: '/compare/vendors?preset=judged' },
]
const ready = computed(() => Boolean(health.value?.primary_workflow_ready))
const selectedProgram = computed(() => programs.value.find(program => program.id === selectedProgramId.value))
const missionProgramId = computed(() => selectedProgramId.value)
const seedCoverage = computed(() => health.value ? `${health.value.required.seed.coverage.primes}P / ${health.value.required.seed.coverage.subcontractors}S` : '—')
const sourceRecords = computed(() => health.value?.source_coverage.reduce((sum, source) => sum + source.records, 0) || 0)
const freshnessDetail = computed(() => {
  const fresh = health.value?.freshness
  if (!fresh) return 'Unavailable'
  if (fresh.age_hours != null) return `${fresh.age_hours}h since latest source retrieval`
  return fresh.latest_retrieved_at || 'No retrieval timestamp reported'
})
function presetLink(preset: any) {
  if (preset.to) return scopedLink(preset.to)
  return { path: '/explorer', query: { mission: preset.title, template: preset.template, root_id: missionProgramId.value, ...preset.params } }
}
function scopedLink(target: string) {
  const [path, search = ''] = target.split('?')
  return { path, query: { ...Object.fromEntries(new URLSearchParams(search)), root_id: missionProgramId.value || undefined } }
}
async function load(refresh = false) {
  status.value = 'loading'; error.value = ''; programError.value = ''
  try {
    if (!ws.loaded) await ws.load()
    health.value = await api.get<ReadinessContract>(`/api/health${refresh ? '?refresh=true' : ''}`)
    try {
      programs.value = (await api.get<{ items: Array<{ id: string; name: string }> }>('/api/graph/programs')).items
      const preferred = selectedProgramId.value
      selectedProgramId.value = programs.value.some(program => program.id === preferred) ? preferred : (programs.value[0]?.id || '')
    } catch (cause) {
      programError.value = cause instanceof Error ? cause.message : 'Program index unavailable.'
    }
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Unknown readiness failure.'
  } finally {
    status.value = 'done'
  }
}
onMounted(() => load())
</script>

<style scoped>
.mission{--ink:#172724;--muted:#65756f;--paper:#f1f0e7;--line:#c8cec2;--teal:#075f58;--signal:#dd5a35;--panel:#f8f7ef;--advisory:#fae6d8;--state:#e5e8df;--simulation:#fff1c9;--simulation-line:#9a6700;--hover:#edf1e9;--focus:#b7791f;--shadow:rgba(20,50,45,.1);min-height:100%;background:var(--paper);color:var(--ink);padding:30px 36px 60px;font-family:Manrope,system-ui,sans-serif}
:global(.v-theme--dark .mission){--ink:#d9e6e1;--muted:#9eb2aa;--paper:#101715;--line:#394943;--teal:#66c6b7;--signal:#ff8a66;--panel:#141d1a;--advisory:#36241e;--state:#182420;--simulation:#352f1b;--simulation-line:#e7bd55;--hover:#1d2b26;--focus:#f0c96b;--shadow:rgba(0,0,0,.35)}
.hero{display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:48px;border-top:7px solid var(--teal);border-bottom:1px solid var(--ink);padding:28px 0}.eyebrow,.section-title span,.metrics span,.decision-card>span,.preset span{font:700 10px ui-monospace,monospace;letter-spacing:.13em;color:var(--teal)}h1{font-size:clamp(36px,5vw,68px);line-height:.98;letter-spacing:-.055em;max-width:980px;margin:12px 0 18px}.hero p{max-width:780px;color:var(--muted);font-size:16px}.hero-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:24px}.speed{display:block;margin-top:9px;color:var(--muted)}.decision-card{align-self:stretch;border-left:1px solid var(--line);padding:14px 0 14px 28px;display:flex;flex-direction:column;gap:14px}.decision-card strong{font-size:27px;line-height:1.05}.decision-card small{color:var(--muted);word-break:break-word}.decision-card .v-chip{align-self:flex-start}.section-title{display:flex;justify-content:space-between;align-items:end;margin:34px 0 14px}.section-title h2{font-size:25px;margin:4px 0 0}.metrics{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);background:var(--panel)}.metrics article{padding:18px;border-right:1px solid var(--line);display:grid;gap:6px}.metrics article:last-child{border:0}.metrics strong{font-size:25px}.metrics small{color:var(--muted)}.sources{display:flex;flex-wrap:wrap;gap:7px;margin-top:8px}.sources span{border:1px solid var(--line);padding:5px 8px;font:10px ui-monospace,monospace}.advisory,.state,.simulation{padding:14px 16px;background:var(--advisory);border-left:5px solid var(--signal);margin-bottom:10px}.advisory{display:flex;gap:10px}.state{background:var(--state);border-color:var(--teal)}.state p{margin:8px 0}.state.failure{background:var(--advisory);border-color:var(--signal)}.preset-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.preset{display:grid;grid-template-columns:30px 1fr 20px;gap:10px;align-items:start;min-height:132px;padding:18px;color:var(--ink);text-decoration:none;border:1px solid var(--line);background:var(--panel);transition:.15s}.preset:hover,.preset:focus-visible{transform:translateY(-2px);border-color:var(--teal);background:var(--hover);box-shadow:0 10px 25px var(--shadow)}.preset:focus-visible,.workflow a:focus-visible{outline:2px solid var(--focus);outline-offset:3px}.preset h3{margin:5px 0;font-size:19px}.preset p{margin:0;color:var(--muted);font-size:12px}.workflow{display:grid;grid-template-columns:repeat(4,1fr);border-top:2px solid var(--ink);border-bottom:1px solid var(--ink)}.workflow a{display:flex;gap:12px;padding:17px;color:var(--ink);text-decoration:none;border-right:1px solid var(--line);transition:background-color .15s}.workflow a:hover,.workflow a:focus-visible{background:var(--hover)}.workflow a:last-child{border:0}.workflow b{font:700 20px ui-monospace,monospace;color:var(--signal)}.workflow span,.workflow strong{display:block}.workflow span{font-size:11px;color:var(--muted)}.workflow strong{color:var(--ink);font-size:13px;margin-bottom:4px}.simulation{display:flex;gap:12px;margin-top:30px;background:var(--simulation);border-color:var(--simulation-line);font-size:12px}.simulation strong{display:block;letter-spacing:.1em;font-size:10px}@media(max-width:1000px){.hero{grid-template-columns:1fr}.decision-card{border-left:0;border-top:1px solid var(--line);padding:20px 0}.metrics,.preset-grid,.workflow{grid-template-columns:1fr 1fr}.metrics article:nth-child(2){border-right:0}.metrics article{border-bottom:1px solid var(--line)}}@media(max-width:650px){.mission{padding:20px 16px 40px}.metrics,.preset-grid,.workflow{grid-template-columns:1fr}.metrics article,.workflow a{border-right:0;border-bottom:1px solid var(--line)}}
</style>