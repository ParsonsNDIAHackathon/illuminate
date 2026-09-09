<template>
  <v-container fluid>
    <v-toolbar color="transparent" density="compact" class="mb-2">
      <v-toolbar-title class="text-h6">Data</v-toolbar-title>
    </v-toolbar>
    <v-tabs :model-value="activeSection" color="primary" class="mb-4" @update:model-value="setSection">
      <v-tab value="entities" prepend-icon="mdi-domain">Entities</v-tab>
      <v-tab value="people" prepend-icon="mdi-account-tie">People</v-tab>
      <v-tab value="artifacts" prepend-icon="mdi-file-document-multiple">Artifacts</v-tab>
      <v-tab value="risk" prepend-icon="mdi-shield-alert-outline">Risk</v-tab>
      <v-tab value="claims" prepend-icon="mdi-check-decagram">Claims</v-tab>
    </v-tabs>
    <v-window :model-value="activeSection">
      <v-window-item value="entities"><Entities v-if="activeSection === 'entities'" embedded /></v-window-item>
      <v-window-item value="people"><People v-if="activeSection === 'people'" embedded /></v-window-item>
      <v-window-item value="artifacts"><Artifacts v-if="activeSection === 'artifacts'" embedded /></v-window-item>
      <v-window-item value="risk"><Risk v-if="activeSection === 'risk'" embedded /></v-window-item>
      <v-window-item value="claims"><Claims v-if="activeSection === 'claims'" embedded /></v-window-item>
    </v-window>
  </v-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import Artifacts from './Artifacts.vue'
import Claims from './Claims.vue'
import Entities from './Entities.vue'
import People from './People.vue'
import Risk from './Risk.vue'

const props = defineProps<{ section?: string }>()
const router = useRouter()
const sections = new Set(['entities', 'people', 'artifacts', 'risk', 'claims'])
const activeSection = computed(() => sections.has(props.section || '') ? props.section! : 'entities')

function setSection(section: unknown) {
  router.push(`/data/${sections.has(String(section)) ? section : 'entities'}`)
}
</script>
