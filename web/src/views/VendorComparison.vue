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
      <v-card-text class="d-flex align-center flex-wrap ga-2">
        <v-text-field v-model="leftId" label="Left vendor entity ID" density="compact" hide-details />
        <v-text-field v-model="rightId" label="Right vendor entity ID" density="compact" hide-details />
        <v-btn color="primary" :loading="loading" :disabled="!leftId.trim() || !rightId.trim()" @click="loadLive">Compare live reports</v-btn>
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
import { useRoute } from 'vue-router'
import { getVendorRiskProfile, type VendorRiskProfile } from '../api/client'
import VendorRiskColumn from '../components/VendorRiskColumn.vue'
import { TRUSTWORTHY_RISKY_PRESET } from '../data/vendorComparisonPreset'

const route = useRoute()
const profiles = ref<[VendorRiskProfile, VendorRiskProfile] | null>(null)
const leftId = ref(String(route.query.left || ''))
const rightId = ref(String(route.query.right || ''))
const loading = ref(false)
const error = ref('')
const asOf = '2026-09-08'
const isPreset = computed(() => profiles.value?.every(profile => profile.sourceMode === 'frozen'))
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
  loading.value = true
  error.value = ''
  try {
    profiles.value = await Promise.all([
      getVendorRiskProfile(leftId.value.trim()),
      getVendorRiskProfile(rightId.value.trim()),
    ]) as [VendorRiskProfile, VendorRiskProfile]
  } catch (cause: any) {
    error.value = `Live comparison unavailable: ${cause.message}. The frozen preset remains available offline.`
  } finally {
    loading.value = false
  }
}
onMounted(() => leftId.value && rightId.value ? loadLive() : loadPreset())
</script>

<style scoped>
.comparison { max-width: 1500px; padding: 24px; }
.grid { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 28px; }
.summary-row { margin-bottom: 12px; }
.category-pair { align-items: stretch; }
@media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
</style>