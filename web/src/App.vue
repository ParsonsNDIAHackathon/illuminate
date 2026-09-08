<template>
  <v-app :theme="ws.theme">
    <v-app-bar density="compact" flat border>
      <v-btn class="nav-trigger" icon="mdi-menu" variant="text" aria-label="Open navigation" @click="drawer = !drawer" />
      <span class="brand">ILLUMINATE</span>
      <!-- What the canvas is showing, not a workspace setting: it follows the focus picker. -->
      <v-chip class="context-chip ml-3" size="small" variant="tonal" :prepend-icon="graph.focusId ? 'mdi-target' : 'mdi-graph-outline'" to="/"
              :title="graph.focusId ? 'The canvas is narrowed to this program — pick Everything to see them all' : 'The canvas shows every program'">
        {{ graph.focusId ? `Program: ${graph.focusLabel || graph.focusId}` : 'All programs' }}
      </v-chip>
      <v-spacer />
      <v-select v-if="route.name === 'graph'" class="depth-select mr-2" :model-value="ws.depth" @update:model-value="ws.setDepth" :items="[1,2,3,4,5,6]" label="Depth" hide-details />
      <v-badge v-if="jobs.running.length" :content="jobs.running.length" color="secondary" inline class="mr-2"><v-icon icon="mdi-cog-sync" size="20" /></v-badge>
      <v-btn :icon="ws.theme === 'dark' ? 'mdi-weather-sunny' : 'mdi-weather-night'" :aria-label="ws.theme === 'dark' ? 'Use light theme' : 'Use dark theme'" variant="text" @click="ws.setTheme(ws.theme === 'dark' ? 'light' : 'dark')" />
      <v-avatar size="28" color="primary" class="ml-1 mr-2"><span class="text-caption">jb</span></v-avatar>
    </v-app-bar>
    <v-navigation-drawer v-model="drawer" :rail="!narrow" :temporary="narrow" :permanent="!narrow" border>
      <v-list density="compact" nav>
        <v-list-item v-for="n in nav" :key="n.to" :to="n.to" :prepend-icon="n.icon" :title="n.title" :value="n.to">
          <template #append v-if="n.badge"><v-badge :content="n.badge" color="warning" inline /></template>
        </v-list-item>
      </v-list>
    </v-navigation-drawer>
    <v-main>
      <router-view />
    </v-main>
    <PermissionDialog />
    <v-snackbar v-model="snack" timeout="4000" location="bottom right">{{ snackText }}</v-snackbar>
  </v-app>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useGraph } from './stores/graph'
import { useDisplay } from 'vuetify'
import { useWorkspace } from './stores/workspace'
import { useChat } from './stores/chat'
import { usePermissions } from './stores/permissions'
import { useJobs } from './stores/jobs'
import { api } from './api/client'
import PermissionDialog from './components/PermissionDialog.vue'
const ws = useWorkspace(); const graph = useGraph(); const chat = useChat(); const perms = usePermissions(); const jobs = useJobs(); const route = useRoute()
const { smAndDown } = useDisplay()
const narrow = smAndDown
const drawer = ref(!narrow.value)
const staged = ref(0); const snack = ref(false); const snackText = ref('')
const nav = computed(() => [
  { to: '/', icon: 'mdi-graph', title: 'Graph' },
  { to: '/entities', icon: 'mdi-domain', title: 'Entities' },
  { to: '/people', icon: 'mdi-account-tie', title: 'People' },
  { to: '/artifacts', icon: 'mdi-file-document-multiple', title: 'Artifacts' },
  { to: '/claims', icon: 'mdi-check-decagram', title: 'Claims', badge: staged.value || undefined },
  { to: '/connectors', icon: 'mdi-power-plug', title: 'Connectors' },
  { to: '/settings', icon: 'mdi-cog', title: 'Settings' },
])
async function refreshStaged() { try { staged.value = (await api.get('/api/claims?status=staged&limit=500')).length } catch {} }
onMounted(async () => { await ws.load(); chat.bind(); perms.load(); jobs.load(); refreshStaged(); setInterval(refreshStaged, 20000) })
watch(() => jobs.jobs.map(j => j.status).join(), (a, b) => { if (a !== b) { const done = jobs.jobs.find(j => ['succeeded', 'empty', 'partial', 'failed', 'timed_out'].includes(j.status)); if (done) { snackText.value = `Enrichment ${done.status}: ${done.entity_name}`; snack.value = true; refreshStaged() } } })
watch(narrow, value => { drawer.value = !value })
</script>
<style>
.brand { font-family: 'IBM Plex Mono', ui-monospace, monospace; letter-spacing: .18em; font-weight: 700; margin-left: 12px; }
html, body { overscroll-behavior: none; }
.nav-trigger { display: none; }
.depth-select { width: 110px; flex: 0 0 110px; }
@media (max-width: 959px) {
  .nav-trigger { display: inline-flex; }
  .brand { margin-left: 2px; font-size: 12px; }
  .context-chip { max-width: min(34vw, 150px); }
  .context-chip .v-chip__content { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .depth-select { width: 76px; flex-basis: 76px; }
  .v-app-bar .v-avatar { display: none; }
}
@media (max-width: 430px) {
  .context-chip { display: none !important; }
  .brand { letter-spacing: .11em; }
}
</style>
