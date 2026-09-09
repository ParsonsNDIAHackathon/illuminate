<template>
  <div class="rail">
    <div class="rail-head">
      <span class="title">Ask the graph</span>
      <v-chip size="x-small" :color="chat.connected ? 'success' : 'error'" variant="tonal">{{ chat.connected ? 'live' : 'offline' }}</v-chip>
      <v-chip v-if="!chat.modelKey" size="x-small" color="warning" variant="tonal" title="No OpenAI key — templates only">templates only</v-chip>
      <v-spacer />
      <v-btn icon="mdi-refresh" variant="text" size="x-small" title="New conversation" @click="chat.reset()" />
    </div>
    <div class="messages" ref="scroller">
      <div v-if="!chat.messages.length" class="empty">
        <p>Ask in plain language — questions are answered against the graph on screen, and the
        canvas restyles itself to match the answer.</p>
        <p class="mt-2">Try:</p>
        <v-chip v-for="s in suggestions" :key="s" class="ma-1" variant="outlined" size="small" @click="ask(s)">{{ s }}</v-chip>
      </div>
      <p v-if="!chat.messages.length" class="empty-foot">Click any node or edge on the canvas to read its properties beside it.</p>
      <div v-for="m in chat.messages" :key="m.id" class="msg" :class="m.role">
        <div v-if="m.role === 'user'" class="bubble user">{{ m.text }}</div>
        <div v-else class="bubble assistant">
          <div v-for="(t, i) in m.tools" :key="i" class="tool">
            <v-icon size="14" :icon="t.ok === undefined ? 'mdi-loading mdi-spin' : t.ok ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'" :color="t.ok === false ? 'error' : undefined" />
            <span class="mono">{{ t.name }}</span>
            <span v-if="t.summary" class="sum">— {{ t.summary }}</span>
            <span v-if="t.permission" class="sum perm">· {{ t.permission.status }}</span>
          </div>
          <div class="text" v-html="render(m.text)"></div>
          <div v-if="m.error" class="error-text">{{ m.error }}</div>
          <v-progress-linear v-if="m.streaming" indeterminate height="2" class="mt-1" />
          <details v-if="m.cypher?.length" class="cy-details">
            <summary>{{ m.cypher.length }} Cypher statement{{ m.cypher.length > 1 ? 's' : '' }} executed</summary>
            <CypherBlock v-for="(c, i) in m.cypher" :key="i" :statement="c.statement" :params="c.params" :notes="c.notes" />
          </details>
        </div>
      </div>
    </div>
    <div class="input">
      <v-textarea v-model="draft" rows="1" auto-grow max-rows="5" density="compact" variant="outlined" hide-details placeholder="Ask about this graph…  ⏎" @keydown.enter.exact.prevent="submit" :disabled="chat.busy" />
      <v-btn icon="mdi-send" variant="tonal" color="primary" :disabled="!draft.trim() || chat.busy" @click="submit" />
    </div>
  </div>
</template>
<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useChat } from '../stores/chat'
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
import CypherBlock from './CypherBlock.vue'
const chat = useChat(); const graph = useGraph(); const ws = useWorkspace()
const draft = ref('')
const scroller = ref<HTMLElement>()
const suggestions = [
  "for all of the program's vendors, highlight goods in purple and services in yellow",
  'highlight all entities that rely on manufacturing in CN, include tier 2 and below',
  'which suppliers have a foreign ultimate parent?',
  'show sole-source suppliers',
  'shared directors across suppliers',
]
chat.bind()
function ask(s: string) { draft.value = s; submit() }
function submit() {
  const t = draft.value.trim(); if (!t) return
  // the focused program travels with the message: "the program" means whatever is on screen
  chat.send(t, [...graph.nodes.keys()], ws.ws.layers, graph.focusId, graph.focusLabel)
  draft.value = ''
}
function esc(s: string) { return s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' } as any)[c]) }
function render(t: string) {
  return esc(t || '').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/\n/g, '<br>')
}
watch(() => chat.messages.map(m => m.text.length + (m.tools?.length || 0)).join(','), () => nextTick(() => { if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight }))
</script>
<style scoped>
.rail { display: flex; flex-direction: column; height: 100%; }
.rail-head { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-bottom: 1px solid rgba(128,128,128,.2); }
.title { font-weight: 600; font-size: 14px; letter-spacing: .01em; }
.messages { flex: 1; overflow-y: auto; padding: 10px; }
.empty { opacity: .8; font-size: 13px; }
.empty :deep(.v-chip) { height: auto; min-height: 26px; white-space: normal; padding: 5px 10px; }
.empty :deep(.v-chip__content) { white-space: normal; line-height: 1.3; }
.empty-foot { margin-top: 14px; font-size: 12px; opacity: .55; }
.msg { margin-bottom: 10px; display: flex; }
.msg.user { justify-content: flex-end; }
.bubble { border-radius: 10px; padding: 8px 10px; font-size: 13px; max-width: 100%; }
.bubble.user { background: rgba(96,165,250,.18); }
.bubble.assistant { background: rgba(128,128,128,.10); width: 100%; }
.tool { font-size: 11px; opacity: .8; display: flex; gap: 6px; align-items: center; margin-bottom: 2px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.sum { opacity: .7; }
.perm { color: #f59e0b; }
.text :deep(code) { font-family: ui-monospace, monospace; font-size: 12px; background: rgba(128,128,128,.15); padding: 0 3px; border-radius: 3px; }
.error-text { color: #f87171; font-size: 12px; }
.cy-details { margin-top: 6px; font-size: 12px; }
.cy-details summary { cursor: pointer; opacity: .7; }
.input { display: flex; gap: 6px; padding: 8px; border-top: 1px solid rgba(128,128,128,.2); align-items: flex-end; }
</style>
