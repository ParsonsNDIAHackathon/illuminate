<template>
  <v-card v-if="graph.selected || graph.selectedEdge" class="selection-card" :class="{ collapsed }" elevation="8">
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
      <Inspector v-if="graph.selected" @expand="$emit('expand', $event)" />
      <EdgeInspector v-else />
    </div>
  </v-card>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Inspector from './Inspector.vue'
import EdgeInspector from './EdgeInspector.vue'
import { useGraph } from '../stores/graph'
const graph = useGraph()
defineEmits<{ (e: 'expand', id: string): void }>()
// Folding is a preference about screen real estate, not about this one node, so it outlives
// the selection and the reload.
const STORAGE_KEY = 'illuminate.selection.collapsed'
const collapsed = ref(localStorage.getItem(STORAGE_KEY) === '1')
watch(collapsed, v => localStorage.setItem(STORAGE_KEY, v ? '1' : '0'))
const headIcon = computed(() => graph.selected ? 'mdi-card-text-outline' : 'mdi-vector-polyline')
const headTitle = computed(() => graph.selected?.name || graph.selectedEdge?.type || '')
function close() { graph.select(null); graph.selectEdge(null) }
</script>
<style scoped>
/* Right of the canvas and clear of the zoom column, starting below the toolbar so the layer
   chips keep their full width, and never tall enough to reach the notes line. */
.selection-card { position: absolute; top: 52px; right: 52px; width: 340px; max-height: calc(100% - 116px); z-index: 6; display: flex; flex-direction: column; border-radius: 8px; }
.selection-card.collapsed { max-height: none; }
.head { display: flex; align-items: flex-start; gap: 6px; padding: 7px 4px 7px 10px; border-bottom: 1px solid rgba(128,128,128,.2); flex: 0 0 auto; }
.selection-card.collapsed .head { border-bottom: none; }
.head-icon { opacity: .6; margin-top: 1px; flex: 0 0 auto; }
.head-title { font-weight: 600; font-size: 14px; line-height: 1.25; overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.selection-card.collapsed .head-title { -webkit-line-clamp: 1; }
.body { overflow-y: auto; min-height: 0; }
</style>
