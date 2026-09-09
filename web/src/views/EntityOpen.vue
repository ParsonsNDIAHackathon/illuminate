<template>
  <!-- An entity link used to open a page of its own. The graph is the detail view now: the
       properties card holds what that page held at a glance, and the long form is a Report
       the user generates and keeps. So a link to an entity puts it on the canvas, selected. -->
  <v-container class="d-flex align-center justify-center" style="height: 60vh">
    <div class="text-center">
      <template v-if="!error">
        <v-progress-circular indeterminate size="26" />
        <p class="text-caption mt-3">Opening on the canvas…</p>
      </template>
      <template v-else>
        <p class="text-body-2 text-error">{{ error }}</p>
        <v-btn class="mt-3" variant="tonal" to="/">Back to the graph</v-btn>
      </template>
    </div>
  </v-container>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'
const props = defineProps<{ id: string }>()
const router = useRouter(); const graph = useGraph(); const ws = useWorkspace()
const error = ref('')
onMounted(async () => {
  if (!ws.loaded) await ws.load()
  try {
    if (!graph.nodes.has(props.id)) await graph.loadNeighbourhood(props.id, ws.depth, ws.ws.layers)
    graph.select(props.id)
    router.replace('/')
  } catch (e: any) {
    error.value = e?.message || String(e)
  }
})
</script>
