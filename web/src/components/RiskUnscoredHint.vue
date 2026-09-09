<!-- A column of em-dashes with no explanation is worse than no column.

     A graph seeded before the scorer existed, or restored from a backup, has never been
     through a pass: every risk cell reads "—" and nothing on the page says whether that
     means "nothing found" or "never looked". This says which, and offers the one action
     that fixes it. It appears only when *every* loaded row is unscored — a mix of scored
     and unscored rows is a real result, not a missing pass, and must not be nagged about. -->
<template>
  <v-alert v-if="show" type="info" variant="tonal" density="compact" class="mb-2">
    <div class="d-flex align-center ga-3">
      <span class="text-body-2">
        Nothing here has been scored yet — the risk column is empty because no pass has run,
        not because these are low risk.
      </span>
      <v-spacer />
      <v-btn size="small" variant="tonal" :loading="busy" prepend-icon="mdi-shield-search" @click="score">
        Score them
      </v-btn>
    </div>
    <div v-if="error" class="text-caption text-error mt-1">{{ error }}</div>
  </v-alert>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../api/client'

const props = defineProps<{ items: any[] }>()
const emit = defineEmits<{ (e: 'scored'): void }>()
const busy = ref(false); const error = ref('')

// `risk_scored_at` is not on these list payloads, so "has a pass run" is inferred from the
// rows themselves: a node the scorer has seen always carries a band, even when its score is
// null because every dimension abstained.
const show = computed(() => props.items.length > 0 && props.items.every(i => !i.risk_band))

async function score() {
  busy.value = true; error.value = ''
  try {
    await api.post('/api/risk/rescore', {})
    emit('scored')
  } catch (e: any) {
    error.value = e?.message || 'the rescore was refused'
  } finally { busy.value = false }
}
</script>
