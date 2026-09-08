<template>
  <a :href="href" target="_blank" rel="noopener" @click="openFrame($event, href)"><slot>{{ href }}</slot></a>
  <SourceFrame v-if="frameUrl" :url="frameUrl" @close="frameUrl = null" />
</template>

<script setup lang="ts">
import SourceFrame from './SourceFrame.vue'
import { useSourceFrame } from '../composables/sourceFrame'
defineProps<{ href: string }>()
const { frameUrl, openFrame } = useSourceFrame()
</script>
