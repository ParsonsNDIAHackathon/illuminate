<template>
  <div class="cypher">
    <div class="head">
      <span class="mono">cypher</span>
      <span v-if="classification" class="cls" :class="classification.toLowerCase()">{{ classification }}</span>
      <v-spacer />
      <v-btn icon="mdi-content-copy" variant="text" size="x-small" @click="copy" />
    </div>
    <pre class="mono">{{ statement }}</pre>
    <pre v-if="params && Object.keys(params).length" class="mono params">{{ JSON.stringify(params) }}</pre>
    <div v-if="notes?.length" class="notes">{{ notes.join(' · ') }}</div>
  </div>
</template>
<script setup lang="ts">
const props = defineProps<{ statement: string; params?: any; classification?: string; notes?: string[] }>()
function copy() { navigator.clipboard?.writeText(props.statement) }
</script>
<style scoped>
.cypher { border: 1px solid rgba(128,128,128,.25); border-radius: 6px; padding: 6px 8px; margin: 6px 0; font-size: 11.5px; background: rgba(128,128,128,.06); }
.head { display: flex; align-items: center; gap: 8px; opacity: .8; }
.mono { font-family: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace; }
pre { white-space: pre-wrap; word-break: break-word; margin: 4px 0 0; }
.params { opacity: .7; }
.notes { opacity: .6; margin-top: 4px; font-size: 11px; }
.cls { font-size: 10px; padding: 1px 6px; border-radius: 4px; background: rgba(128,128,128,.2); }
.cls.write, .cls.destructive { background: rgba(220,38,38,.25); }
</style>
