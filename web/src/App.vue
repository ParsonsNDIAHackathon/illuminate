<template>
  <v-app :theme="ws.theme">
    <v-app-bar density="compact" flat border>
      <span class="brand">ILLUMINATE</span>
      <!-- What the canvas is showing, not a workspace setting: it follows the focus picker.
           Unfocused is the default, so it goes unsaid and the space carries the simulation
           notice instead — where it cannot sit on top of the graph. -->
      <v-chip v-if="graph.focusId" class="ml-3" size="small" variant="tonal" prepend-icon="mdi-target" to="/"
              title="The canvas is narrowed to this program — pick Everything to see them all">
        Program: {{ graph.focusLabel || graph.focusId }}
      </v-chip>
      <v-chip v-if="ws.simulated || graph.hasSimulated" class="simulated-badge ml-3" size="small" variant="flat" prepend-icon="mdi-flask-outline"
              title="Scenario material for analysis — not an allegation or verified finding. Simulated nodes, edges and evidence are badged SIM throughout.">
        Simulated data
      </v-chip>
      <v-spacer />
      <v-badge v-if="jobs.running.length" :content="jobs.running.length" color="secondary" inline class="mr-2"><v-icon icon="mdi-cog-sync" size="20" /></v-badge>
      <v-tooltip text="Show Help Page" location="bottom">
        <template #activator="{ props }">
          <v-btn v-bind="props" icon="mdi-help-circle-outline" variant="text" @click="help = true" />
        </template>
      </v-tooltip>
      <v-btn :icon="ws.theme === 'dark' ? 'mdi-weather-sunny' : 'mdi-weather-night'" variant="text" @click="ws.setTheme(ws.theme === 'dark' ? 'light' : 'dark')" />
      <v-avatar size="28" color="primary" class="ml-1 mr-2"><span class="text-caption">jb</span></v-avatar>
    </v-app-bar>
    <v-navigation-drawer rail permanent border>
      <v-list density="compact" nav>
        <v-tooltip v-for="n in nav" :key="n.to" :text="n.title" location="right">
          <template #activator="{ props }">
            <v-list-item v-bind="props" :to="n.to" :prepend-icon="n.icon" :title="n.title" :value="n.to">
              <template #append v-if="n.badge"><v-badge :content="n.badge" color="warning" inline /></template>
            </v-list-item>
          </template>
        </v-tooltip>
      </v-list>
      <!-- The deck is a separate static page, not a route: leave the app where it is and open it
           beside itself, so a demo can cut back to a live canvas without reloading anything. -->
      <template #append>
        <v-list density="compact" nav>
          <v-tooltip text="Open the pitch deck in a new tab" location="right">
            <template #activator="{ props }">
              <v-list-item v-bind="props" href="/slides/" target="_blank" rel="noopener"
                           prepend-icon="mdi-presentation" title="Deck" />
            </template>
          </v-tooltip>
        </v-list>
      </template>
    </v-navigation-drawer>
    <v-main>
      <router-view />
    </v-main>
    <PermissionDialog />
    <HelpDialog v-model="help" />
    <v-snackbar v-model="snack" timeout="4000" location="bottom right">{{ snackText }}</v-snackbar>
  </v-app>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useGraph } from './stores/graph'
import { useWorkspace } from './stores/workspace'
import { useChat } from './stores/chat'
import { usePermissions } from './stores/permissions'
import { useJobs } from './stores/jobs'
import { api } from './api/client'
import PermissionDialog from './components/PermissionDialog.vue'
import HelpDialog from './components/HelpDialog.vue'
const ws = useWorkspace(); const graph = useGraph(); const chat = useChat(); const perms = usePermissions(); const jobs = useJobs()
const staged = ref(0); const snack = ref(false); const snackText = ref(''); const help = ref(false)
const nav = computed(() => [
  { to: '/', icon: 'mdi-graph', title: 'Graph' },
  { to: '/reports', icon: 'mdi-file-chart-outline', title: 'Reports' },
  { to: '/data', icon: 'mdi-database-outline', title: 'Data', badge: staged.value || undefined },
  { to: '/settings', icon: 'mdi-cog', title: 'Settings' },
])
async function refreshStaged() { try { staged.value = (await api.get('/api/claims?status=staged&limit=500')).length } catch {} }
onMounted(async () => { await ws.load(); chat.bind(); perms.load(); jobs.load(); refreshStaged(); setInterval(refreshStaged, 20000) })
watch(() => jobs.jobs.map(j => j.status).join(), (a, b) => { if (a !== b) { const done = jobs.jobs.find(j => j.status === 'done'); if (done) { snackText.value = `Enrichment done: ${done.entity_name}`; snack.value = true; refreshStaged() } } })
</script>
<style>
.brand { font-family: 'IBM Plex Mono', ui-monospace, monospace; letter-spacing: .18em; font-weight: 700; margin-left: 12px; }
.simulated-badge { background: #fff4cf; color: #563b00; border: 1px solid #9a6700; font-weight: 600; letter-spacing: .04em; }
html, body { overscroll-behavior: none; }
</style>
