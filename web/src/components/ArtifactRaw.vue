<template>
  <v-dialog :model-value="!!artifactId" max-width="960" scrollable @update:model-value="v => { if (!v) $emit('close') }">
    <v-card v-if="artifactId">
      <v-card-title class="d-flex align-center ga-2">
        <v-chip size="x-small" variant="tonal">{{ data?.artifact?.kind || 'artifact' }}</v-chip>
        <span class="text-subtitle-1 title">{{ data?.artifact?.title || artifactId }}</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="$emit('close')" />
      </v-card-title>
      <v-card-subtitle class="d-flex flex-wrap ga-3">
        <span v-if="data?.artifact?.source">{{ data.artifact.source }}</span>
        <a v-if="data?.artifact?.url" :href="data.artifact.url" target="_blank" rel="noopener">source page ↗</a>
        <span v-if="data?.artifact?.retrieved_at">retrieved {{ String(data.artifact.retrieved_at).slice(0, 10) }}</span>
        <span class="mono">{{ artifactId }}</span>
      </v-card-subtitle>
      <v-card-text>
        <div v-if="loading" class="py-6 text-center"><v-progress-circular indeterminate size="24" /></div>
        <template v-else-if="data">
          <section>
            <h4>Node properties</h4>
            <pre class="json">{{ pretty(data.artifact) }}</pre>
          </section>
          <section v-if="data.about?.length || data.claims?.length">
            <h4>Attached to</h4>
            <div class="text-body-2">
              <span v-for="e in data.about" :key="e.id" class="mr-3"><router-link :to="`/entities/${e.id}`" @click="$emit('close')">{{ e.name }}</router-link></span>
              <span v-if="data.claims?.length" class="text-caption">· evidences {{ data.claims.length }} claim{{ data.claims.length === 1 ? '' : 's' }}</span>
            </div>
          </section>
          <section v-for="(r, i) in data.raw" :key="i">
            <h4 class="d-flex align-center ga-2">
              Raw payload <span class="text-caption" style="text-transform:none;letter-spacing:0">· {{ r.match }}</span>
              <v-spacer />
              <v-btn size="x-small" variant="text" prepend-icon="mdi-content-copy" @click="copy(r.body)">copy</v-btn>
            </h4>
            <div class="text-caption mono mb-1"><a :href="r.url" target="_blank" rel="noopener">{{ r.url }}</a><span v-if="r.retrieved_at"> · cached {{ String(r.retrieved_at).slice(0, 10) }}</span></div>
            <pre class="json">{{ pretty(r.body) }}</pre>
          </section>
          <p v-if="!data.raw?.length" class="text-body-2 mt-3" style="opacity:.7">No cached source payload for this artifact. It was recorded from a source that is not cached locally (a bulk list, a web page) or its cache entry has expired; the source page link above is still the record of origin.</p>
        </template>
        <p v-else-if="error" class="text-body-2 text-error">{{ error }}</p>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
import { api } from '../api/client'
const props = defineProps<{ artifactId: string | null }>()
defineEmits<{ (e: 'close'): void }>()
const data = ref<any>(null); const loading = ref(false); const error = ref('')
watch(() => props.artifactId, async (id) => {
  data.value = null; error.value = ''
  if (!id) return
  loading.value = true
  try { data.value = await api.get(`/api/artifacts/${encodeURIComponent(id)}`) }
  catch (e: any) { error.value = e?.message || String(e) }
  finally { loading.value = false }
}, { immediate: true })
function pretty(v: any) { try { return JSON.stringify(v, null, 2) } catch { return String(v) } }
async function copy(v: any) { try { await navigator.clipboard.writeText(pretty(v)) } catch {} }
</script>
<style scoped>
.title { overflow-wrap: anywhere; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; opacity: .8; overflow-wrap: anywhere; }
section { margin-top: 14px; }
h4 { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; opacity: .7; margin-bottom: 4px; }
.json { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.45; max-height: 420px; overflow: auto; padding: 10px 12px; border-radius: 6px; background: rgba(128,128,128,.12); white-space: pre; }
</style>
