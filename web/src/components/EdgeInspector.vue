<template>
  <div class="inspector" v-if="edge">
    <div class="d-flex align-center ga-2 mb-1">
      <v-chip size="x-small" variant="tonal">edge · {{ edge.type }}</v-chip>
    </div>
    <div class="ends text-body-2">
      <a href="#" @click.prevent="graph.select(edge.source)">{{ sourceName }}</a>
      <span class="arrow">→</span>
      <a href="#" @click.prevent="graph.select(edge.target)">{{ targetName }}</a>
    </div>
    <section v-if="facts.length">
      <h4>Details</h4>
      <dl>
        <template v-for="[k, v] in facts" :key="k"><dt>{{ k }}</dt><dd>{{ v }}</dd></template>
      </dl>
    </section>
    <section>
      <h4>Provenance</h4>
      <dl>
        <dt>Source</dt><dd>{{ p.source || '—' }} <a v-if="p.source_url" :href="p.source_url" target="_blank" rel="noopener">↗</a></dd>
        <dt>Retrieved</dt><dd>{{ (p.retrieved_at || '').slice(0, 10) || '—' }}</dd>
        <dt>Method</dt><dd>{{ p.method || '—' }}<span v-if="p.confidence != null"> · confidence {{ p.confidence }}</span></dd>
        <template v-if="p.claim_id"><dt>Claim</dt><dd class="mono">{{ p.claim_id }}</dd></template>
        <dt>Edge id</dt><dd class="mono">{{ edge.id }}</dd>
      </dl>
    </section>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useGraph } from '../stores/graph'
const graph = useGraph()
const edge = computed(() => graph.selectedEdge)
const p = computed(() => edge.value?.props || {})
const sourceName = computed(() => graph.nodes.get(edge.value?.source || '')?.name || edge.value?.source)
const targetName = computed(() => graph.nodes.get(edge.value?.target || '')?.name || edge.value?.target)
// Provenance fields have their own section; everything else the edge carries is a fact about the relationship.
const PROVENANCE = new Set(['id', 'source', 'source_url', 'retrieved_at', 'method', 'confidence', 'claim_id', 'simulated'])
const facts = computed(() => Object.entries(p.value)
  .filter(([k, v]) => !PROVENANCE.has(k) && v !== null && v !== undefined && v !== '')
  .map(([k, v]) => [k.replace(/_/g, ' '), typeof v === 'boolean' ? (v ? 'yes' : 'no') : Array.isArray(v) ? v.join(', ') : String(v)] as [string, string]))
</script>
<style scoped>
.inspector { padding: 10px 12px 12px; font-size: 13px; }
.ends { margin: 4px 0 2px; line-height: 1.4; overflow-wrap: anywhere; }
.ends a { text-decoration: none; }
.arrow { opacity: .5; margin: 0 6px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; opacity: .8; }
section { margin-top: 10px; }
h4 { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; opacity: .6; margin-bottom: 4px; }
dl { display: grid; grid-template-columns: 90px 1fr; gap: 2px 8px; margin: 0; }
dt { opacity: .6; text-transform: capitalize; } dd { margin: 0; overflow-wrap: anywhere; }
</style>
