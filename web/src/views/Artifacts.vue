<template>
  <v-container fluid>
    <div class="d-flex align-center ga-2 mb-2"><h2 class="text-h6">Artifacts</h2><v-select v-model="kind" :items="['', 'award', 'registry', 'filing', 'news', 'web', 'record', 'document']" label="kind" hide-details style="max-width: 160px" /><v-spacer /><span class="text-caption">{{ items.length }} evidence artifacts</span></div>
    <v-data-table :items="items" :headers="headers" density="compact" :items-per-page="50" :loading="loading">
      <template #item.title="{ item }"><a :href="item.url" target="_blank" rel="noopener">{{ item.title }}</a></template>
      <template #item.about="{ item }"><router-link v-for="a in item.about" :key="a.id" :to="`/entities/${a.id}`" class="mr-2">{{ a.name }}</router-link></template>
      <template #item.amount="{ item }">{{ item.amount ? '$' + Number(item.amount).toLocaleString() : '' }}</template>
    </v-data-table>
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api, qs } from '../api/client'
const kind = ref(''); const items = ref<any[]>([]); const loading = ref(false)
const headers = [{ title: 'Kind', key: 'kind', width: 90 }, { title: 'Title', key: 'title' }, { title: 'About', key: 'about' }, { title: 'Source', key: 'source', width: 110 }, { title: 'Date', key: 'published_at', width: 110 }, { title: 'Amount', key: 'amount', width: 130 }, { title: 'Claims', key: 'claims', width: 80 }]
async function load() { loading.value = true; try { items.value = await api.get(`/api/artifacts?${qs({ kind: kind.value, limit: 500 })}`) } finally { loading.value = false } }
watch(kind, load); onMounted(load)
</script>
