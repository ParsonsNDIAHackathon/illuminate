<template>
  <a :href="href" target="_blank" rel="noopener" @click="openFrame($event, href)"><slot>{{ href }}</slot></a>
  <SourceFrame v-if="frameUrl" :url="frameUrl" :artifact-id="artifactId" @close="frameUrl = null" />
</template>

<script setup lang="ts">
import SourceFrame from './SourceFrame.vue'
import { useSourceFrame } from '../composables/sourceFrame'
// With the artifact known, the frame can show its document or its record when the page
// itself serves neither; a bare link can only frame the page.
defineProps<{ href: string; artifactId?: string | null }>()
const { frameUrl, openFrame } = useSourceFrame()
</script>
