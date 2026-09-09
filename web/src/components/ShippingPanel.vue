<template>
  <section v-if="shipping.visible" class="shipping-panel" aria-label="Shipping routes">
    <div class="shipping-heading">
      <strong>Shipping routes</strong>
      <span>{{ shipping.routes.length }} {{ shipping.routes.length === 1 ? 'record' : 'records' }} · {{ suppliers }} {{ suppliers === 1 ? 'supplier' : 'suppliers' }} · {{ customers }} {{ customers === 1 ? 'destination' : 'destinations' }} in this graph scope</span>
      <v-btn size="x-small" variant="text" :loading="shipping.loading" @click="shipping.load()">Refresh</v-btn>
    </div>
    <v-alert v-if="shipping.error" type="warning" variant="tonal" density="compact" role="alert">Shipping routes could not be loaded. Use Refresh to retry. <span v-if="shipping.catalog.routes.length">Previously loaded records remain visible.</span></v-alert>
    <p v-if="shipping.routes.some(x => x.route.status === 'illustrative')" class="shipping-notice">Illustrative routes are hypothetical examples, not evidence of actual shipments. Alternative records do not represent separate shipments.</p>
    <div class="shipping-controls">
      <v-select v-model="shipping.status" :items="statuses" label="Route evidence" density="compact" variant="outlined" hide-details />
      <v-select v-model="shipping.port" :items="ports" label="Port dependency" density="compact" variant="outlined" hide-details />
      <v-select :model-value="shipping.selectedId" :items="routeOptions" label="Inspect route" density="compact" variant="outlined" hide-details @update:model-value="shipping.select($event)" />
    </div>
    <p v-if="!shipping.loading && !shipping.routes.length" role="status" class="shipping-notice">{{ shipping.error ? 'No shipping records available.' : 'No linked routes match this graph scope and filters. Try Everything, clear search, or change the evidence and port filters.' }}</p>
    <p v-else class="shipping-legend">Solid teal: confirmed · Dashed amber: inferred · Dotted violet: illustrative. Lines show approximate ocean corridors, not live vessel tracks.</p>
    <v-dialog :model-value="!!shipping.selected" max-width="660" @update:model-value="!$event && shipping.select('')">
      <v-card v-if="shipping.selected" class="route-card">
        <v-card-title class="route-title">{{ shipping.selected.route.name }}</v-card-title>
        <v-card-text>
          <v-chip size="small" :color="shipping.selected.route.status === 'confirmed' ? 'success' : 'warning'">{{ shipping.selected.route.status }}</v-chip>
          <p class="mt-3">{{ shipping.selected.supplier.name }} → {{ shipping.selected.customer.name }}</p>
          <p class="text-caption mt-1">Linked SUPPLIES relationship. Route evidence is separate from evidence of the supplier relationship.</p>
          <dl class="route-facts">
            <dt>Goods</dt><dd>{{ shipping.selected.route.goods }}</dd>
            <dt>Journey</dt><dd><div v-for="(segment, i) in shipping.selected.route.segments" :key="i">{{ portName(segment.from_port) }} → {{ portName(segment.to_port) }}<span v-if="segment.passages.length"> · {{ segment.passages.join(', ') }}</span></div></dd>
            <dt>Source</dt><dd>{{ shipping.selected.route.source.title }}<br><a v-if="sourceLink" :href="sourceLink" target="_blank" rel="noopener noreferrer">Open route evidence ↗</a><span v-else>{{ shipping.selected.route.source.reference }}</span></dd>
            <dt>Updated</dt><dd>{{ shipping.selected.route.updated_at }} · Record date, not a live position</dd>
            <dt>Evidence notes</dt><dd>{{ shipping.selected.route.notes }}</dd>
          </dl>
          <p class="text-caption">This overlay does not change vendor risk scores. News country mentions do not establish that a route is disrupted.</p>
        </v-card-text>
        <v-card-actions class="route-actions">
          <v-btn size="small" @click="inspectSupplier">Inspect supplier</v-btn>
          <v-btn size="small" @click="inspectRelationship">View supplier relationship</v-btn>
          <v-spacer /><v-btn size="small" @click="shipping.select('')">Close</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useShipping } from '../stores/shipping'
import { useGraph } from '../stores/graph'
import { usesPort } from '../shippingMap'
const shipping = useShipping(), graph = useGraph()
const statuses = [{ title: 'All evidence', value: '' }, { title: 'Confirmed', value: 'confirmed' }, { title: 'Inferred', value: 'inferred' }, { title: 'Illustrative', value: 'illustrative' }]
const ports = computed(() => [{ title: 'All ports', value: '' }, ...shipping.ports.map(p => ({ title: `${p.name} (${shipping.filtered.filter(x => usesPort(x.route, p.id)).length})`, value: p.id }))])
const routeOptions = computed(() => [{ title: 'Select a route', value: '' }, ...shipping.routes.map(x => ({ title: `${x.route.name} · ${x.route.status}`, value: x.route.id }))])
const suppliers = computed(() => new Set(shipping.routes.map(x => x.supplier.id)).size)
const customers = computed(() => new Set(shipping.routes.map(x => x.customer.id)).size)
const sourceLink = computed(() => {
  try { const url = new URL(shipping.selected?.route.source.reference || ''); return ['https:', 'http:'].includes(url.protocol) ? url.href : '' } catch { return '' }
})
function portName(id: string) { return shipping.catalog.ports.find(p => p.id === id)?.name || id }
function inspectSupplier() { if (shipping.selected) graph.select(shipping.selected.supplier.id); shipping.select('') }
function inspectRelationship() { if (shipping.selected) graph.selectEdge(shipping.selected.edge.id); shipping.select('') }
watch(() => shipping.ports, ports => { if (!ports.some(p => p.id === shipping.port)) shipping.port = '' })
watch(() => shipping.routes, routes => { if (!routes.some(x => x.route.id === shipping.selectedId)) shipping.select('') })
onMounted(() => { if (!shipping.attempted) shipping.load() })
</script>
<style scoped>
.shipping-panel { flex-shrink:0; padding:10px 0 4px; border-bottom:1px solid rgba(128,128,128,.25); }
.shipping-heading { display:flex; align-items:center; gap:10px; flex-wrap:wrap; font-size:12px; }
.shipping-heading span { opacity:.75; font-size:11px; }
.shipping-controls { display:flex; gap:8px; margin-top:8px; }
.shipping-controls > * { min-width:0; flex:1; }
.shipping-controls > :last-child { flex:1.6; }
.shipping-notice,.shipping-legend { font-size:11px; margin-top:6px; line-height:1.5; }
.shipping-notice { color:rgb(var(--v-theme-warning)); }
.shipping-legend { opacity:.75; }
.route-title { white-space:normal; padding-top:20px; }
.route-facts { display:grid; grid-template-columns:100px 1fr; gap:12px; margin:20px 0; font-size:13px; }
.route-facts dt { opacity:.65; }.route-facts dd { overflow-wrap:anywhere; }
.route-actions { flex-wrap:wrap; }
@media(max-width:900px) { .shipping-controls { flex-wrap:wrap; }.shipping-controls > * { flex-basis:160px; }.shipping-controls > :last-child { flex-basis:100%; } }
</style>
