<template>
  <router-link :to="{ path: '/explorer', query: { ...route.query, root_id: graph.focusId || undefined, view: 'map', map_location: code } }" :title="`View ${code} on the map`">{{ label || code }}</router-link>
</template>
<script setup lang="ts">
import { useGraph } from '../stores/graph'
import { useRoute } from 'vue-router'
defineProps<{ code: string; label?: string }>()
const route = useRoute()
const graph = useGraph()
</script>
