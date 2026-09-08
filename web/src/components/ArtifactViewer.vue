<template>
  <v-dialog :model-value="!!artifactId" max-width="1100" scrollable @update:model-value="v => { if (!v) $emit('close') }">
    <v-card v-if="artifactId" class="viewer">
      <v-card-title class="d-flex align-center ga-2">
        <v-chip size="x-small" variant="tonal">{{ art?.kind || 'artifact' }}</v-chip>
        <span class="text-subtitle-1 title">{{ art?.title || artifactId }}</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="$emit('close')" />
      </v-card-title>
      <v-card-subtitle class="d-flex flex-wrap ga-3">
        <span v-if="art?.source">{{ art.source }}</span>
        <a v-if="art?.url" :href="art.url" target="_blank" rel="noopener" @click="openFrame($event, art.url)">source page ↗</a>
        <span v-if="art?.published_at">published {{ String(art.published_at).slice(0, 10) }}</span>
        <span v-if="art?.retrieved_at">retrieved {{ String(art.retrieved_at).slice(0, 10) }}</span>
        <span class="mono">{{ artifactId }}</span>
      </v-card-subtitle>

      <v-tabs v-model="tab" density="compact">
        <v-tab value="details">Details</v-tab>
        <v-tab value="document">Document</v-tab>
        <v-tab value="raw">Raw JSON</v-tab>
      </v-tabs>

      <v-card-text>
        <div v-if="loading" class="py-6 text-center"><v-progress-circular indeterminate size="24" /></div>
        <p v-else-if="error" class="text-body-2 text-error">{{ error }}</p>
        <v-window v-else-if="data" v-model="tab">

          <v-window-item value="details">
            <section v-if="data.about?.length || data.claims?.length">
              <h4>Attached to</h4>
              <div class="text-body-2">
                <router-link v-for="e in data.about" :key="e.id" :to="`/entities/${e.id}`" class="mr-3" @click="$emit('close')">{{ e.name }}</router-link>
              </div>
              <div v-if="data.claims?.length" class="text-caption mt-1">
                evidences {{ data.claims.length }} claim{{ data.claims.length === 1 ? '' : 's' }}:
                <span v-for="c in data.claims" :key="c.id" class="mr-2">{{ c.predicate }}<span v-if="c.status !== 'committed'"> ({{ c.status }})</span></span>
              </div>
            </section>
            <ArtifactSummary :summary="data.summary" />
          </v-window-item>

          <v-window-item value="document">
            <SourceDocument :doc="doc" :file-url="fileUrl" :loading="docLoading">
              <template #actions>
                <v-btn v-if="doc?.url" size="x-small" variant="text" :href="doc.url" target="_blank" rel="noopener" append-icon="mdi-open-in-new" @click="openFrame($event, doc.url)">open source</v-btn>
              </template>
              <template #fallback-link>
                <a v-if="doc?.url" :href="doc.url" target="_blank" rel="noopener" class="ml-1" @click="openFrame($event, doc.url)">open the source page ↗</a>
              </template>
            </SourceDocument>
          </v-window-item>

          <v-window-item value="raw">
            <section v-for="(r, i) in data.raw" :key="i">
              <h4 class="d-flex align-center ga-2">
                Cached payload <span class="text-caption" style="text-transform:none;letter-spacing:0">· {{ r.match }}</span>
                <v-spacer />
                <v-btn size="x-small" variant="text" prepend-icon="mdi-content-copy" @click="copy(r.body)">copy</v-btn>
              </h4>
              <div class="text-caption mono mb-1"><a :href="r.url" target="_blank" rel="noopener">{{ r.url }}</a><span v-if="r.retrieved_at"> · cached {{ String(r.retrieved_at).slice(0, 10) }}</span></div>
              <pre class="json">{{ pretty(r.body) }}</pre>
            </section>
            <section>
              <h4>Node properties</h4>
              <pre class="json">{{ pretty(art) }}</pre>
            </section>
            <p v-if="!data.raw?.length" class="text-body-2 mt-3" style="opacity:.7">No cached source payload for this artifact. It was recorded from a source that is not cached locally (a bulk list, a web page) or its cache entry has expired; the source page link above is still the record of origin.</p>
          </v-window-item>

        </v-window>
      </v-card-text>
    </v-card>
    <SourceFrame v-if="frameUrl" :url="frameUrl" @close="frameUrl = null" />
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '../api/client'
import SourceFrame from './SourceFrame.vue'
import SourceDocument from './SourceDocument.vue'
import ArtifactSummary from './ArtifactSummary.vue'
import { useSourceFrame } from '../composables/sourceFrame'
const props = defineProps<{ artifactId: string | null }>()
const { frameUrl, openFrame } = useSourceFrame()
defineEmits<{ (e: 'close'): void }>()

const data = ref<any>(null); const loading = ref(false); const error = ref('')
const doc = ref<any>(null); const docLoading = ref(false)
const tab = ref('details')
const art = computed(() => data.value?.artifact)
const fileUrl = computed(() => `/api/artifacts/${encodeURIComponent(props.artifactId || '')}/file`)

watch(() => props.artifactId, async (id) => {
  data.value = null; doc.value = null; error.value = ''; tab.value = 'details'
  if (!id) return
  loading.value = true
  try { data.value = await api.get(`/api/artifacts/${encodeURIComponent(id)}`) }
  catch (e: any) { error.value = e?.message || String(e) }
  finally { loading.value = false }
}, { immediate: true })

// The document is fetched from its source, so it waits until the tab is actually opened.
watch(tab, async (t) => {
  const id = props.artifactId
  if (t !== 'document' || !id || doc.value || docLoading.value) return
  docLoading.value = true
  try { doc.value = await api.get(`/api/artifacts/${encodeURIComponent(id)}/content`) }
  catch (e: any) { doc.value = { status: 'error', note: e?.message || String(e), url: art.value?.url } }
  finally { docLoading.value = false }
})

function pretty(v: any) { try { return JSON.stringify(v, null, 2) } catch { return String(v) } }
async function copy(v: any) { try { await navigator.clipboard.writeText(pretty(v)) } catch {} }
</script>

<style scoped>
.title { overflow-wrap: anywhere; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; opacity: .8; overflow-wrap: anywhere; }
section { margin-top: 14px; }
h4 { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; opacity: .7; margin-bottom: 4px; }
dl { display: grid; grid-template-columns: 190px 1fr; gap: 3px 12px; margin: 0; font-size: 13px; }
dt { opacity: .6; } dd { margin: 0; overflow-wrap: anywhere; }
.warn { color: rgb(var(--v-theme-warning)); font-weight: 600; }
.json { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.45; max-height: 420px; overflow: auto; padding: 10px 12px; border-radius: 6px; background: rgba(128, 128, 128, .12); white-space: pre; }
</style>
