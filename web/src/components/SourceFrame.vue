<template>
  <v-dialog :model-value="open" width="92vw" max-width="1400" scrollable @update:model-value="v => { if (!v) $emit('close') }">
    <v-card v-if="open" class="d-flex flex-column" style="height: 88vh">
      <v-card-title class="d-flex align-center ga-2">
        <v-chip size="x-small" variant="tonal">{{ hostOf(href) || 'source' }}</v-chip>
        <span class="url">{{ href || artifactId }}</span>
        <v-spacer />
        <v-btn v-if="href" size="small" variant="text" :href="href" target="_blank" rel="noopener" append-icon="mdi-open-in-new">open in new tab</v-btn>
        <v-btn icon="mdi-close" variant="text" size="small" @click="$emit('close')" />
      </v-card-title>

      <!-- Three ways to show an original, in order of fidelity: the document itself as its
           type reads, the live page in a frame, or — for a site that serves no document and
           refuses to be embedded — the record the artifact was made from. -->
      <v-card-text v-if="mode === 'document'" class="flex-grow-1">
        <SourceDocument :doc="doc" :file-url="fileUrl" :loading="loading" height="calc(88vh - 190px)" />
      </v-card-text>

      <v-card-text v-else-if="mode === 'frame'" class="pa-0 flex-grow-1">
        <iframe class="frame" :src="href!" referrerpolicy="no-referrer"
                sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
                title="Original source" />
      </v-card-text>

      <v-card-text v-else class="flex-grow-1">
        <v-alert type="info" variant="tonal" density="compact" class="mb-3">
          <div class="text-body-2">{{ doc?.note || 'This page serves no document.' }}</div>
          <div class="text-caption mt-1">{{ hostOf(href) }} will not display inside another page, so the record it was
            captured from is shown here — open it in a new tab for the page itself.</div>
        </v-alert>
        <div v-if="summaryLoading" class="py-6 text-center"><v-progress-circular indeterminate size="24" /></div>
        <ArtifactSummary v-else-if="summary" :summary="summary" />
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '../api/client'
import SourceDocument from './SourceDocument.vue'
import ArtifactSummary from './ArtifactSummary.vue'
import { hostOf } from '../composables/sourceFrame'
const props = defineProps<{ url?: string | null; artifactId?: string | null }>()
defineEmits<{ (e: 'close'): void }>()

const doc = ref<any>(null); const loading = ref(false)
const summary = ref<any>(null); const summaryLoading = ref(false)
const open = computed(() => !!(props.url || props.artifactId))
const href = computed(() => doc.value?.url || props.url || null)
const fileUrl = computed(() => `/api/artifacts/${encodeURIComponent(props.artifactId || '')}/file`)

const mode = computed(() => {
  if (!props.artifactId) return 'frame'
  if (loading.value || (doc.value?.status === 'ok' && doc.value.render !== 'binary')) return 'document'
  return doc.value?.frameable && href.value ? 'frame' : 'record'
})

watch(() => props.artifactId, async (id) => {
  doc.value = null; summary.value = null
  if (!id) return
  loading.value = true
  try { doc.value = await api.get(`/api/artifacts/${encodeURIComponent(id)}/content`) }
  catch (e: any) { doc.value = { status: 'error', note: e?.message || String(e) } }
  finally { loading.value = false }
}, { immediate: true })

// The recorded fields are only fetched for the artifacts that fall back to them.
watch(mode, async (m) => {
  const id = props.artifactId
  if (m !== 'record' || !id || summary.value || summaryLoading.value) return
  summaryLoading.value = true
  try { summary.value = (await api.get(`/api/artifacts/${encodeURIComponent(id)}`))?.summary }
  catch { summary.value = null }
  finally { summaryLoading.value = false }
}, { immediate: true })
</script>

<style scoped>
.url { overflow-wrap: anywhere; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; opacity: .8; }
.frame { display: block; width: 100%; height: 100%; border: 0; background: #fff; }
</style>
