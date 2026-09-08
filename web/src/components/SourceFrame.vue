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

      <!-- Behind an artifact the fetched document is shown in its natural form —
           rendered HTML, PDF, image, text. A bare URL, or a page that refuses to be
           fetched server-side, is framed live instead. -->
      <v-card-text v-if="showDoc" class="flex-grow-1">
        <SourceDocument :doc="doc" :file-url="fileUrl" :loading="loading" height="calc(88vh - 190px)" />
      </v-card-text>
      <v-card-text v-else class="pa-0 flex-grow-1">
        <iframe class="frame" :src="href!" referrerpolicy="no-referrer"
                sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
                title="Original source" />
      </v-card-text>

      <v-card-subtitle v-if="!showDoc" class="py-2 text-caption" style="opacity:.6">
        <span v-if="doc?.note">{{ doc.note }} </span>
        <span>Showing the live page — a site that refuses to be framed will look blank; open it in a new tab instead.</span>
      </v-card-subtitle>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '../api/client'
import SourceDocument from './SourceDocument.vue'
import { hostOf } from '../composables/sourceFrame'
const props = defineProps<{ url?: string | null; artifactId?: string | null }>()
defineEmits<{ (e: 'close'): void }>()

const doc = ref<any>(null); const loading = ref(false)
const open = computed(() => !!(props.url || props.artifactId))
const href = computed(() => props.url || doc.value?.url || null)
const fileUrl = computed(() => `/api/artifacts/${encodeURIComponent(props.artifactId || '')}/file`)
// A document worth showing, or nothing to fall back to: otherwise frame the live page.
const showDoc = computed(() => !!props.artifactId &&
  (loading.value || !href.value || (doc.value?.status === 'ok' && doc.value.render !== 'binary')))

watch(() => props.artifactId, async (id) => {
  doc.value = null
  if (!id) return
  loading.value = true
  try { doc.value = await api.get(`/api/artifacts/${encodeURIComponent(id)}/content`) }
  catch (e: any) { doc.value = { status: 'error', note: e?.message || String(e) } }
  finally { loading.value = false }
}, { immediate: true })
</script>

<style scoped>
.url { overflow-wrap: anywhere; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; opacity: .8; }
.frame { display: block; width: 100%; height: 100%; border: 0; background: #fff; }
</style>
