<template>
  <v-dialog :model-value="!!url" width="92vw" max-width="1400" scrollable @update:model-value="v => { if (!v) $emit('close') }">
    <v-card v-if="url" class="d-flex flex-column" style="height: 88vh">
      <v-card-title class="d-flex align-center ga-2">
        <v-chip size="x-small" variant="tonal">{{ hostOf(url) || 'source' }}</v-chip>
        <span class="url">{{ url }}</span>
        <v-spacer />
        <v-btn size="small" variant="text" :href="url" target="_blank" rel="noopener" append-icon="mdi-open-in-new">open in new tab</v-btn>
        <v-btn icon="mdi-close" variant="text" size="small" @click="$emit('close')" />
      </v-card-title>
      <v-card-text class="pa-0 flex-grow-1">
        <iframe class="frame" :src="url" referrerpolicy="no-referrer"
                sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
                title="Original source" />
      </v-card-text>
      <v-card-subtitle class="py-2 text-caption" style="opacity:.6">
        A site that refuses to be framed shows up blank here — open it in a new tab (ctrl/⌘-click the link) instead.
      </v-card-subtitle>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { hostOf } from '../composables/sourceFrame'
defineProps<{ url: string | null }>()
defineEmits<{ (e: 'close'): void }>()
</script>

<style scoped>
.url { overflow-wrap: anywhere; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; opacity: .8; }
.frame { display: block; width: 100%; height: 100%; border: 0; background: #fff; }
</style>
