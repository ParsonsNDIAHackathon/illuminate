<template>
  <v-app :theme="ws.theme">
    <v-app-bar density="compact" flat border>
      <v-btn class="nav-trigger" icon="mdi-menu" variant="text" aria-label="Open navigation" @click="drawer = !drawer" />
      <span class="brand">ILLUMINATE</span>
      <!-- What the canvas is showing, not a workspace setting: it follows the focus picker.
           Unfocused is the default, so it goes unsaid and the space carries the simulation
           notice instead — where it cannot sit on top of the graph or push every page down. -->
      <v-chip v-if="graph.focusId" class="context-chip ml-3" size="small" variant="tonal" prepend-icon="mdi-target" to="/"
              title="The canvas is narrowed to this program — pick Everything to see them all">
        Program: {{ graph.focusLabel || graph.focusId }}
      </v-chip>
      <v-chip v-if="graph.hasSimulated" class="simulated-badge ml-3" size="small" variant="flat" prepend-icon="mdi-flask-outline"
              title="Scenario material for analysis — not an allegation or verified finding. Simulated nodes, edges and evidence are badged SIM throughout.">
        Simulated data
      </v-chip>
      <v-spacer />
      <v-select v-if="route.name === 'graph'" class="depth-select mr-2" :model-value="ws.depth" @update:model-value="ws.setDepth" :items="[1,2,3,4,5,6]" label="Depth" hide-details />
      <v-badge v-if="jobs.running.length" :content="jobs.running.length" color="secondary" inline class="mr-2"><v-icon icon="mdi-cog-sync" size="20" /></v-badge>
      <v-btn :icon="ws.theme === 'dark' ? 'mdi-weather-sunny' : 'mdi-weather-night'" :aria-label="ws.theme === 'dark' ? 'Use light theme' : 'Use dark theme'" variant="text" @click="ws.setTheme(ws.theme === 'dark' ? 'light' : 'dark')" />
      <v-avatar size="28" color="primary" class="ml-1 mr-2"><span class="text-caption">jb</span></v-avatar>
    </v-app-bar>
    <v-navigation-drawer v-model="drawer" :rail="!narrow" :temporary="narrow" :permanent="!narrow" border>
      <v-list density="compact" nav aria-label="Product navigation">
        <v-list-item :to="withContext('/')" prepend-icon="mdi-target" title="Start mission" value="mission" color="primary" />
        <v-list-item :to="withContext('/explorer')" prepend-icon="mdi-graph-outline" title="Mission graph" value="graph" />
        <v-menu location="end" :close-on-content-click="true">
          <template #activator="{ props }"><v-list-item v-bind="props" prepend-icon="mdi-database-outline" title="Supporting records" :active="recordsNav.some(item => item.to === route.path)" /></template>
          <v-list density="compact" nav aria-label="Supporting records">
            <v-list-item v-for="n in recordsNav" :key="n.to" :to="withContext(n.to)" :prepend-icon="n.icon" :title="n.title" :value="n.to">
              <template #append v-if="n.badge"><v-badge :content="n.badge" color="warning" inline /></template>
            </v-list-item>
          </v-list>
        </v-menu>
        <v-list-item :to="withContext('/settings')" prepend-icon="mdi-cog-outline" title="Administration" value="administration" :active="route.path === '/settings' || route.path === '/connectors'" />
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
import { useRoute, type LocationQueryRaw } from 'vue-router'
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
const recordsNav = computed(() => [
  { to: '/entities', icon: 'mdi-domain', title: 'Entities' },
  { to: '/programs', icon: 'mdi-clipboard-text-outline', title: 'Programs' },
  { to: '/people', icon: 'mdi-account-tie', title: 'People' },
  { to: '/artifacts', icon: 'mdi-file-document-multiple-outline', title: 'Evidence' },
  { to: '/claims', icon: 'mdi-check-decagram-outline', title: 'Evidence review', badge: staged.value || undefined },
  { to: '/interoperability', icon: 'mdi-database-export-outline', title: 'Share findings' },
])
function contextQuery(): LocationQueryRaw {
  const keys = ['root_id', 'program', 'vendor', 'focus', 'finding', 'family', 'evidence']
  const query: LocationQueryRaw = {}
  for (const key of keys) if (route.query[key] != null) query[key] = route.query[key]
  if (!query.root_id && graph.focusId) query.root_id = graph.focusId
  return query
}
function withContext(path: string) { return { path, query: contextQuery() } }
async function refreshStaged() { try { staged.value = (await api.get('/api/claims?status=staged&limit=500')).length } catch {} }
onMounted(async () => { await ws.load(); chat.bind(); perms.load(); jobs.load(); refreshStaged(); setInterval(refreshStaged, 20000) })
watch(() => jobs.jobs.map(j => j.status).join(), (a, b) => { if (a !== b) { const done = jobs.jobs.find(j => ['succeeded', 'empty', 'partial', 'failed', 'timed_out'].includes(j.status)); if (done) { snackText.value = `Enrichment ${done.status}: ${done.entity_name}`; snack.value = true; refreshStaged() } } })
watch(narrow, value => { drawer.value = !value })
</script>
<style>
.brand { font-family: 'IBM Plex Mono', ui-monospace, monospace; letter-spacing: .18em; font-weight: 700; margin-left: 12px; }
.simulated-badge { background: #fff4cf; color: #563b00; border: 1px solid #9a6700; font-weight: 600; letter-spacing: .04em; }
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
  .simulated-badge { margin-left: 6px !important; }
  .brand { letter-spacing: .11em; }
}
</style>
