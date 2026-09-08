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
        <a v-if="art?.url" :href="art.url" target="_blank" rel="noopener">source page ↗</a>
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
            <section v-for="(sec, i) in data.summary?.sections || []" :key="i">
              <h4>{{ sec.title }}</h4>
              <div v-if="sec.source_note" class="text-caption mb-1" style="opacity:.6">{{ sec.source_note }}</div>
              <dl>
                <template v-for="f in sec.fields" :key="f.label">
                  <dt>{{ f.label }}</dt>
                  <dd>
                    <a v-if="f.href" :href="f.href" target="_blank" rel="noopener">{{ f.value }}</a>
                    <span v-else :class="f.emphasis === 'warn' ? 'warn' : ''">{{ f.value }}</span>
                  </dd>
                </template>
              </dl>
              <div v-if="sec.note" class="text-caption mt-1" style="opacity:.6">{{ sec.note }}</div>
            </section>
            <p v-if="!data.summary?.sections?.length" class="text-body-2" style="opacity:.7">This artifact carries no fields beyond its id.</p>
          </v-window-item>

          <v-window-item value="document">
            <div v-if="docLoading" class="py-6 text-center"><v-progress-circular indeterminate size="24" /><div class="text-caption mt-2">fetching the source document…</div></div>
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
                <v-btn v-if="doc.url" size="x-small" variant="text" :href="doc.url" target="_blank" rel="noopener" append-icon="mdi-open-in-new">open source</v-btn>
              </div>

              <iframe v-if="doc.render === 'html' && htmlView === 'rendered'" class="frame" sandbox="" referrerpolicy="no-referrer" :srcdoc="doc.html" title="Source document" />
              <pre v-else-if="doc.render === 'html'" class="doc">{{ doc.text || '(no text content)' }}</pre>
              <embed v-else-if="doc.render === 'pdf'" class="frame" :src="fileUrl" type="application/pdf" />
              <img v-else-if="doc.render === 'image'" :src="fileUrl" class="shot" alt="Source document" />
              <pre v-else-if="doc.render === 'text'" class="doc">{{ doc.text }}</pre>
              <p v-else-if="doc.render === 'binary'" class="text-body-2" style="opacity:.75">{{ doc.note }}</p>

              <p v-if="doc.truncated || doc.text_truncated || doc.capped" class="text-caption mt-2" style="opacity:.6">
                Document truncated for display — open the source link for the whole of it.
              </p>
              <p v-if="doc.status !== 'ok'" class="text-body-2" style="opacity:.75">
                {{ doc.note }}
                <a v-if="doc.url" :href="doc.url" target="_blank" rel="noopener" class="ml-1">open the source page ↗</a>
              </p>
            </template>
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
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '../api/client'
const props = defineProps<{ artifactId: string | null }>()
defineEmits<{ (e: 'close'): void }>()

const data = ref<any>(null); const loading = ref(false); const error = ref('')
const doc = ref<any>(null); const docLoading = ref(false)
const tab = ref('details'); const htmlView = ref<'rendered' | 'text'>('rendered')
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
.json, .doc { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.45; max-height: 420px; overflow: auto; padding: 10px 12px; border-radius: 6px; background: rgba(128, 128, 128, .12); }
.json { white-space: pre; }
.doc { white-space: pre-wrap; max-height: 62vh; }
.frame { width: 100%; height: 62vh; border: 1px solid rgba(128, 128, 128, .3); border-radius: 6px; background: #fff; }
.shot { max-width: 100%; border-radius: 6px; }
</style>
