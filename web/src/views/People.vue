<template>
  <v-container fluid>
    <div class="d-flex align-center ga-2 mb-2"><h2 class="text-h6">People</h2><v-text-field v-model="q" placeholder="filter" hide-details style="max-width: 280px" clearable /><v-spacer /><span class="text-caption">{{ items.length }} people · one HELD_ROLE edge per tenure</span></div>
    <v-data-table :items="items" :headers="headers" density="compact" :items-per-page="50" :loading="loading">
      <template #item.name="{ item }">{{ item.name }} <v-chip v-if="item.simulated" size="x-small" color="warning" variant="tonal" class="ml-1">SIM</v-chip><v-chip v-if="item.entities > 1" size="x-small" color="secondary" variant="tonal" class="ml-1">interlock</v-chip></template>
      <template #item.roles="{ item }">
        <div v-for="r in item.roles" :key="r.edge_id" class="text-body-2">
          <router-link :to="`/entities/${r.entity_id}`">{{ r.entity }}</router-link> — {{ r.title }} <span class="text-caption" style="opacity:.7">{{ r.role_type }} · {{ r.from || '?' }} – {{ r.current ? 'now' : (r.to || '?') }}</span>
        </div>
      </template>
      <template #item.source="{ item }"><a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noopener">{{ item.source }}</a><span v-else>{{ item.source }}</span></template>
    </v-data-table>
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api, qs } from '../api/client'
const q = ref(''); const items = ref<any[]>([]); const loading = ref(false)
const headers = [{ title: 'Person', key: 'name' }, { title: 'Roles (tenured)', key: 'roles' }, { title: 'Entities', key: 'entities', width: 90 }, { title: 'Source', key: 'source', width: 120 }]
async function load() { loading.value = true; try { items.value = await api.get(`/api/people?${qs({ q: q.value, limit: 500 })}`) } finally { loading.value = false } }
let t: any; watch(q, () => { clearTimeout(t); t = setTimeout(load, 250) }); onMounted(load)
</script>
