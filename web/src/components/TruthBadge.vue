<template>
  <v-chip size="x-small" variant="tonal" :color="color">{{ text }}</v-chip>
</template>
<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ value: string }>()
const normalized = computed(() => (props.value || 'unknown').toLowerCase())
const text = computed(() => (normalized.value === 'committed' ? 'VERIFIED' : normalized.value.replaceAll('_', ' ').toUpperCase()))
const color = computed(() => ({
  committed: 'success', verified: 'success', current: 'success',
  derived: 'info', superseded: 'info', staged: 'warning', stale: 'warning', diligence_required: 'warning',
  rejected: 'error', conflicting: 'error', unsupported: 'error',
  simulated: 'warning', missing: 'warning', unavailable: 'warning',
}[normalized.value]))
</script>