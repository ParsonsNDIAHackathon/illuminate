<template>
  <div v-if="loading" class="py-6 text-center"><v-progress-circular indeterminate size="24" /><div class="text-caption mt-2">fetching the source document…</div></div>
  <template v-else-if="doc">
    <div class="d-flex align-center ga-2 mb-2 flex-wrap">
      <v-chip size="x-small" variant="tonal">{{ doc.content_type || doc.status }}</v-chip>
      <span v-if="doc.bytes" class="text-caption">{{ (doc.bytes / 1024).toFixed(0) }} KB</span>
      <span v-if="doc.retrieved_at" class="text-caption">fetched {{ String(doc.retrieved_at).slice(0, 10) }}</span>
      <v-spacer />
      <v-btn-toggle v-if="doc.render === 'html'" v-model="htmlView" density="compact" variant="outlined" mandatory>
        <v-btn value="rendered" size="x-small">Rendered</v-btn>
        <v-btn value="text" size="x-small">Text</v-btn>
      </v-btn-toggle>
      <slot name="actions" />
    </div>

    <iframe v-if="doc.render === 'html' && htmlView === 'rendered'" class="frame" :style="frameStyle" sandbox="" referrerpolicy="no-referrer" :srcdoc="doc.html" title="Source document" />
    <pre v-else-if="doc.render === 'html'" class="doc" :style="frameStyle">{{ doc.text || '(no text content)' }}</pre>
    <embed v-else-if="doc.render === 'pdf'" class="frame" :style="frameStyle" :src="fileUrl" type="application/pdf" />
    <img v-else-if="doc.render === 'image'" :src="fileUrl" class="shot" alt="Source document" />
    <pre v-else-if="doc.render === 'text'" class="doc" :style="frameStyle">{{ doc.text }}</pre>
    <p v-else-if="doc.render === 'binary'" class="text-body-2" style="opacity:.75">{{ doc.note }}</p>

    <p v-if="doc.truncated || doc.text_truncated || doc.capped" class="text-caption mt-2" style="opacity:.6">
      Document truncated for display — open the source link for the whole of it.
    </p>
    <p v-if="doc.status !== 'ok'" class="text-body-2" style="opacity:.75">
      {{ doc.note }}
      <slot name="fallback-link" />
    </p>
  </template>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
const props = defineProps<{ doc: any; fileUrl: string; loading?: boolean; height?: string }>()
const htmlView = ref<'rendered' | 'text'>('rendered')
const frameStyle = computed(() => (props.height ? { height: props.height, maxHeight: props.height } : undefined))
</script>

<style scoped>
.doc { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.45; padding: 10px 12px; border-radius: 6px; background: rgba(128, 128, 128, .12); white-space: pre-wrap; max-height: 62vh; overflow: auto; }
.frame { width: 100%; height: 62vh; border: 1px solid rgba(128, 128, 128, .3); border-radius: 6px; background: #fff; }
.shot { max-width: 100%; border-radius: 6px; }
</style>
