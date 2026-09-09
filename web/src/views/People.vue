<template>
  <v-container fluid :class="embedded ? 'pa-0' : undefined">
    <v-toolbar color="transparent" density="compact" class="mb-2">
      <v-toolbar-title v-if="!embedded" class="text-h6">People</v-toolbar-title>
      <v-text-field v-model="q" placeholder="filter" hide-details style="max-width: 280px" clearable />
      <v-spacer /><v-chip size="small" variant="text">{{ items.length }} people · one HELD_ROLE edge per tenure</v-chip>
    </v-toolbar>
    <RiskUnscoredHint :items="items" @scored="load" />
    <!-- A row opens the person; a link inside it (an employer) goes where it says. -->
    <v-data-table class="people-table" :items="items" :headers="headers" density="compact" :items-per-page="50" :loading="loading" hover
                  @click:row="(e: MouseEvent, r: any) => { if (!(e.target as HTMLElement)?.closest('a')) router.push(`/people/${r.item.id}`) }">
      <template #item.risk_score="{ item }">
        <v-chip size="x-small" variant="tonal" :color="bandChip(item.risk_band)"
                :title="`${bandLabel(item.risk_band)} · ${item.risk_top_factor || 'no leading factor'} · ${confidenceNote(item.risk_confidence, item.risk_dimensions_scored, item.risk_dimensions_requested)}`">
          {{ item.risk_score ?? '—' }}<span v-if="isThin(item.risk_confidence)">?</span>
        </v-chip>
      </template>
      <template #item.name="{ item }"><router-link :to="`/people/${item.id}`">{{ item.name }}</router-link> <v-chip v-if="item.flagged" size="x-small" color="error" variant="tonal" class="ml-1">flagged</v-chip><v-chip v-if="item.entities > 1" size="x-small" color="secondary" variant="tonal" class="ml-1">interlock</v-chip></template>
      <template #item.roles="{ item }">
        <div v-for="r in item.roles" :key="r.edge_id" class="text-body-2">
          <router-link :to="`/entities/${r.entity_id}`">{{ r.entity }}</router-link> — {{ r.title }} <span class="text-caption" style="opacity:.7">{{ r.role_type }} · {{ r.from || '?' }} – {{ r.current ? 'now' : (r.to || '?') }}</span>
        </div>
      </template>
      <template #item.source="{ item }"><a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noopener">{{ item.source }}</a><span v-else>{{ item.source }}</span></template>
      <template #item.view="{ item }"><v-btn icon="mdi-graph" size="x-small" variant="text" title="Open on the canvas" @click.stop="openOnCanvas(item.id, 'Person')" /></template>
    </v-data-table>
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, qs } from '../api/client'
import RiskUnscoredHint from '../components/RiskUnscoredHint.vue'
import { bandChip, bandLabel, confidenceNote, isThin } from '../styles/risk'
import { useOpenOnCanvas } from '../composables/openOnCanvas'
defineProps<{ embedded?: boolean }>()
const router = useRouter(); const { openOnCanvas } = useOpenOnCanvas()
const q = ref(''); const items = ref<any[]>([]); const loading = ref(false)
const headers = [{ title: 'Risk', key: 'risk_score', width: 80 }, { title: 'Person', key: 'name' }, { title: 'Roles (tenured)', key: 'roles' },
                 { title: 'Leading factor', key: 'risk_top_factor' }, { title: 'Entities', key: 'entities', width: 90 }, { title: 'Source', key: 'source', width: 120 },
                 { title: '', key: 'view', width: 44, sortable: false }]
async function load() { loading.value = true; try { items.value = await api.get(`/api/people?${qs({ q: q.value, limit: 500 })}`) } finally { loading.value = false } }
let t: any; watch(q, () => { clearTimeout(t); t = setTimeout(load, 250) }); onMounted(load)
</script>
