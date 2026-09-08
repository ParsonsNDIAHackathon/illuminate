<template>
  <section v-for="(sec, i) in summary?.sections || []" :key="i">
    <h4>{{ sec.title }}</h4>
    <div v-if="sec.source_note" class="text-caption mb-1" style="opacity:.6">{{ sec.source_note }}</div>
    <dl>
      <template v-for="f in sec.fields" :key="f.label">
        <dt>{{ f.label }}</dt>
        <dd>
          <a v-if="f.href" :href="f.href" target="_blank" rel="noopener" @click="openFrame($event, f.href)">{{ f.value }}</a>
          <span v-else :class="f.emphasis === 'warn' ? 'warn' : ''">{{ f.value }}</span>
        </dd>
      </template>
    </dl>
    <div v-if="sec.note" class="text-caption mt-1" style="opacity:.6">{{ sec.note }}</div>
  </section>
  <p v-if="!summary?.sections?.length" class="text-body-2" style="opacity:.7">This artifact carries no fields beyond its id.</p>
  <SourceFrame v-if="frameUrl" :url="frameUrl" @close="frameUrl = null" />
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { useSourceFrame } from '../composables/sourceFrame'
// Loaded lazily: the frame shows this summary back when a page refuses to be embedded.
const SourceFrame = defineAsyncComponent(() => import('./SourceFrame.vue'))
defineProps<{ summary: any }>()
const { frameUrl, openFrame } = useSourceFrame()
</script>

<style scoped>
section { margin-top: 14px; }
h4 { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; opacity: .7; margin-bottom: 4px; }
dl { display: grid; grid-template-columns: 190px 1fr; gap: 3px 12px; margin: 0; font-size: 13px; }
dt { opacity: .6; } dd { margin: 0; overflow-wrap: anywhere; }
.warn { color: rgb(var(--v-theme-warning)); font-weight: 600; }
</style>
