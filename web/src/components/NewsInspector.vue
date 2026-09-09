<template>
  <div class="pa-3 news-inspector" v-if="news.selected">
    <div class="d-flex align-center ga-2 mb-2">
      <v-chip size="x-small" variant="tonal">News · {{ news.selected.providers?.join(' + ') || news.selected.provider || 'GDELT' }}</v-chip>
      <v-spacer />
      <v-btn icon="mdi-close" aria-label="Close news inspector" variant="text" size="x-small" @click="news.selectedUrl = null" />
    </div>
    <h3 class="text-subtitle-1 font-weight-bold">{{ news.selected.title || news.selected.url }}</h3>
    <ArtifactSummary :summary="preview?.summary" />
    <div class="d-flex flex-wrap ga-2 mt-3">
      <v-btn size="small" variant="tonal" prepend-icon="mdi-file-document-outline" @click="viewing = true">View article details</v-btn>
      <SourceLink :href="news.selected.url">Open source ↗</SourceLink>
    </div>
    <ArtifactViewer :artifact-id="null" :preview="viewing ? preview : null" @close="viewing = false" />
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useNews } from '../stores/news'
import { mapNews, newsPreview } from '../newsMap'
import world from '../data/worldMap.json'
import regions from '../data/mapRegions.json'
import ArtifactSummary from './ArtifactSummary.vue'
import ArtifactViewer from './ArtifactViewer.vue'
import SourceLink from './SourceLink.vue'
const news = useNews()
const viewing = ref(false)
const preview = computed(() => news.selected ? newsPreview(news.selected, mapNews([news.selected], world, regions).places.map(place => place.name)) : null)
watch(() => news.selectedUrl, () => { viewing.value = false })
</script>

<style scoped>
.news-inspector { min-width:0; overflow-wrap:anywhere; }
.news-inspector :deep(dl) { grid-template-columns:110px minmax(0, 1fr); }
</style>
