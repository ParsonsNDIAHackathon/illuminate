<template>
  <v-container fluid class="comparison">
    <div class="d-flex align-center flex-wrap ga-2 mb-2">
      <div>
        <h1 class="text-h5">Vendor risk comparison</h1>
        <p class="text-body-2" style="opacity:.72">Aligned UC-11 categories. Scores prioritize review; they are not proof of wrongdoing.</p>
      </div>
      <v-spacer />
      <v-btn prepend-icon="mdi-snowflake" variant="tonal" @click="loadPreset">Load judged preset</v-btn>
    </div>
    <v-alert v-if="isPreset" type="info" variant="tonal" density="compact" class="mb-3">
      Offline judged case · frozen {{ asOf }} · all vendor names and evidence are simulated calibration data.
    </v-alert>
    <v-card variant="outlined" class="mb-4">
      <v-card-text class="picker-grid">
        <v-autocomplete v-model="leftId" :items="candidates" item-title="name" item-value="id" label="First vendor" placeholder="Search by vendor name" :loading="candidatesLoading" :disabled="loading" clearable no-data-text="No matching vendors" density="compact">
          <template #item="{ props: itemProps, item }"><v-list-item v-bind="itemProps" :subtitle="item.raw.identityLine"><template #append><v-chip v-if="item.raw.ambiguous" size="x-small" color="warning">AMBIGUOUS NAME</v-chip></template><div class="match-context">{{ item.raw.matchContext }}</div></v-list-item></template>
          <template #selection="{ item }"><span>{{ item.raw.name }} <small>— {{ item.raw.identityLine }}</small></span></template>
        </v-autocomplete>
        <v-autocomplete v-model="rightId" :items="candidates" item-title="name" item-value="id" label="Comparator vendor" placeholder="Search by vendor name" :loading="candidatesLoading" :disabled="loading" clearable no-data-text="No matching vendors" density="compact">
          <template #item="{ props: itemProps, item }"><v-list-item v-bind="itemProps" :subtitle="item.raw.identityLine"><template #append><v-chip v-if="item.raw.ambiguous" size="x-small" color="warning">AMBIGUOUS NAME</v-chip></template><div class="match-context">{{ item.raw.matchContext }}</div></v-list-item></template>
          <template #selection="{ item }"><span>{{ item.raw.name }} <small>— {{ item.raw.identityLine }}</small></span></template>
        </v-autocomplete>
        <v-btn color="primary" :loading="loading" :disabled="!canCompare" @click="loadLive">Compare live reports</v-btn>
        <p v-if="leftId && !rightId" class="picker-help">First vendor preserved. Choose a comparator by name; identifiers and match context appear before selection.</p>
        <p v-else-if="leftId && leftId === rightId" class="picker-help error-copy">Choose two different legal records.</p>
      </v-card-text>
    </v-card>
    <v-alert v-if="error" type="error" variant="tonal" closable class="mb-3" @click:close="error = ''">{{ error }}</v-alert>
    <div v-if="profiles">
      <div class="grid summary-row">
        <VendorRiskColumn :profile="profiles[0]" />
        <VendorRiskColumn :profile="profiles[1]" />
      </div>
      <div v-for="category in categoryOrder" :key="category.id" class="grid category-pair">
        <VendorRiskColumn :profile="profiles[0]" :category="category" />
        <VendorRiskColumn :profile="profiles[1]" :category="category" />
      </div>
    </div>
  </v-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, getVendorRiskProfile, qs, type EntityListResponse, type EntitySummary, type VendorRiskProfile } from '../api/client'
import VendorRiskColumn from '../components/VendorRiskColumn.vue'
import { TRUSTWORTHY_RISKY_PRESET } from '../data/vendorComparisonPreset'
import { vendorCandidates } from '../lib/vendorIdentity'

const route = useRoute()
const router = useRouter()
const profiles = ref<[VendorRiskProfile, VendorRiskProfile] | null>(null)
const leftId = ref(String(route.query.left || ''))
const rightId = ref(String(route.query.right || ''))
const rootId = computed(() => String(route.query.root_id || ''))
const loading = ref(false)
const candidatesLoading = ref(false)
const entities = ref<EntitySummary[]>([])
const error = ref('')
const asOf = '2026-09-08'
const isPreset = computed(() => profiles.value?.every(profile => profile.sourceMode === 'frozen'))
const candidates = computed(() => vendorCandidates(entities.value))
const canCompare = computed(() => Boolean(leftId.value?.trim() && rightId.value?.trim() && leftId.value !== rightId.value))
const categoryOrder = computed(() => {
  const seen = new Map<string, { id: string; label?: string; weight: number }>()
  for (const profile of profiles.value || []) for (const category of profile.categories) {
    if (!seen.has(category.id)) seen.set(category.id, { id: category.id, label: category.label, weight: category.weight })
  }
  return [...seen.values()]
})

function loadPreset() {
  profiles.value = structuredClone(TRUSTWORTHY_RISKY_PRESET)
  error.value = ''
}
async function loadLive() {
  const selectedLeft = leftId.value.trim()
  const selectedRight = rightId.value.trim()
  loading.value = true
  error.value = ''
  try {
    const liveProfiles = await Promise.all([
      getVendorRiskProfile(selectedLeft, undefined, rootId.value),
      getVendorRiskProfile(selectedRight, undefined, rootId.value),
    ]) as [VendorRiskProfile, VendorRiskProfile]
    if (leftId.value !== selectedLeft || rightId.value !== selectedRight) return
    profiles.value = liveProfiles.map(profile => {
      const candidate = entities.value.find(entity => entity.id === profile.id)
      return {
        ...profile,
        uei: profile.uei || candidate?.uei,
        cage: profile.cage || candidate?.cage,
        lei: profile.lei || candidate?.lei,
        tier: profile.tier ?? candidate?.tier,
      }
    }) as [VendorRiskProfile, VendorRiskProfile]
    await router.replace({ query: { ...route.query, preset: undefined, left: selectedLeft, right: selectedRight } })
  } catch (cause: any) {
    error.value = `Live comparison unavailable: ${cause.message}. The frozen preset remains available offline.`
  } finally {
    loading.value = false
  }
}
async function loadCandidates() {
  candidatesLoading.value = true
  try {
    const result = await api.get<EntityListResponse>(`/api/entities?${qs({ kind: 'organization', root_id: rootId.value, limit: 1000 })}`)
    const items = [...result.items]
    while (items.length < result.total) {
      const page = await api.get<EntityListResponse>(`/api/entities?${qs({ kind: 'organization', root_id: rootId.value, limit: 1000, offset: items.length })}`)
      if (!page.items.length) break
      items.push(...page.items)
    }
    entities.value = items
  } catch (cause: any) {
    error.value = `Vendor picker unavailable: ${cause.message}`
  } finally {
    candidatesLoading.value = false
  }
}
onMounted(async () => {
  await loadCandidates()
  if (leftId.value && rightId.value) await loadLive()
  else if (route.query.preset === 'judged' && !leftId.value && !rightId.value) loadPreset()
})
</script>

<style scoped>
.comparison { max-width: 1500px; padding: 24px; }
.grid { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 28px; }
.summary-row { margin-bottom: 12px; }
.category-pair { align-items: stretch; }
.picker-grid { display: grid; grid-template-columns: minmax(280px,1fr) minmax(280px,1fr) auto; gap: 10px; align-items: start; }
.picker-help { grid-column: 1 / -1; margin: -4px 0 0; font-size: 12px; opacity: .75; }
.error-copy { color: #b3261e; opacity: 1; }
.match-context { padding: 0 16px 8px; font-size: 11px; color: #8a5213; font-weight: 600; }
@media (max-width: 960px) { .picker-grid { grid-template-columns: 1fr; } }
@media (max-width: 800px) { .comparison { padding: 14px !important; } .grid { grid-template-columns: 1fr; gap: 14px; } }
@media (max-width: 520px) { .comparison :deep(.v-card-text) { align-items: stretch !important; flex-direction: column; } }
</style>