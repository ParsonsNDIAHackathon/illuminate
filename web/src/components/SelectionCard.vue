<template>
  <v-card v-if="news.selected || graph.selected || graph.selectedEdge" class="selection-card" :class="{ collapsed }" elevation="8">
    <!-- The header stays readable when the body is folded away, so a parked card still says
         what is selected rather than becoming an anonymous strip. -->
    <div class="head" :title="headTitle">
      <v-icon size="16" :icon="headIcon" class="head-icon" />
      <span class="head-title">{{ headTitle }}</span>
      <v-spacer />
      <v-btn :icon="collapsed ? 'mdi-chevron-down' : 'mdi-minus'" variant="text" size="x-small" density="comfortable"
             :title="collapsed ? 'Show properties' : 'Collapse'" @click="collapsed = !collapsed" />
      <v-btn icon="mdi-close" variant="text" size="x-small" density="comfortable" title="Clear selection" @click="close" />
    </div>
    <div v-if="!collapsed" class="body">
      <NewsInspector v-if="news.selected" />
      <Inspector v-else-if="graph.selected" @expand="$emit('expand', $event)" />
      <EdgeInspector v-else />
    </div>
  </v-card>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Inspector from './Inspector.vue'
import NewsInspector from './NewsInspector.vue'
import { useNews } from '../stores/news'
import EdgeInspector from './EdgeInspector.vue'
import { useGraph } from '../stores/graph'
const graph = useGraph()
const news = useNews()
defineEmits<{ (e: 'expand', id: string): void }>()
// Folding is a preference about screen real estate, not about this one node, so it outlives
// the selection and the reload.
const STORAGE_KEY = 'illuminate.selection.collapsed'
const collapsed = ref(localStorage.getItem(STORAGE_KEY) === '1')
watch(collapsed, v => localStorage.setItem(STORAGE_KEY, v ? '1' : '0'))
const headIcon = computed(() => news.selected ? 'mdi-newspaper-variant-outline' : graph.selected ? 'mdi-card-text-outline' : 'mdi-vector-polyline')
const headTitle = computed(() => news.selected?.title || news.selected?.url || graph.selected?.name || graph.selectedEdge?.type || '')
function close() { news.selectedUrl = null; graph.select(null); graph.selectEdge(null) }
</script>
<style scoped>
/* Hard against the right edge, which the canvas tool column used to hold, and never tall
   enough to reach the notes line below it. */
.selection-card { position: absolute; top: 8px; right: 12px; width: 340px; max-height: calc(100% - 72px); z-index: 6; display: flex; flex-direction: column; border-radius: 8px; }
.selection-card.collapsed { max-height: none; }
.head { display: flex; align-items: flex-start; gap: 6px; padding: 7px 4px 7px 10px; border-bottom: 1px solid rgba(128,128,128,.2); flex: 0 0 auto; }
.selection-card.collapsed .head { border-bottom: none; }
.head-icon { opacity: .6; margin-top: 1px; flex: 0 0 auto; }
.head-title { font-weight: 600; font-size: 14px; line-height: 1.25; overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.selection-card.collapsed .head-title { -webkit-line-clamp: 1; }
.body { overflow-y: auto; min-height: 0; }
</style>
