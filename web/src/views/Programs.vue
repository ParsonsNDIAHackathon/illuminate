<template>
  <v-container style="max-width: 1100px">
    <div class="d-flex flex-wrap align-center ga-3 mb-4">
      <div>
        <h1 class="text-h5">Government programs</h1>
        <p class="text-body-2 text-medium-emphasis">Browse program records and open their intelligence reports.</p>
      </div>
      <v-spacer />
      <v-btn color="primary" prepend-icon="mdi-plus" @click="dialog = true">Add program</v-btn>
    </div>

    <v-text-field v-model="q" label="Search programs" placeholder="Name, agency, or program code"
      prepend-inner-icon="mdi-magnify" clearable hide-details class="mb-4" />
    <v-alert v-if="loadError" type="error" variant="tonal" class="mb-4">
      {{ loadError }} <v-btn variant="text" size="small" @click="load">Try again</v-btn>
    </v-alert>
    <v-skeleton-loader v-if="loading && !items.length" type="list-item-three-line@3" />
    <v-card v-else-if="!items.length && !loadError" variant="outlined">
      <v-empty-state icon="mdi-clipboard-search-outline" title="No programs found"
        :text="q ? 'Try a different search.' : 'Add the first government program to this workspace.'" />
    </v-card>
    <v-row v-else>
      <v-col v-for="program in items" :key="program.id" cols="12" md="6">
        <v-card :to="`/entities/${program.id}`" variant="outlined" height="100%">
          <v-card-title class="text-subtitle-1">{{ program.name }}</v-card-title>
          <v-card-subtitle>{{ [program.agency, program.program_code].filter(Boolean).join(' · ') || 'No identifier provided' }}</v-card-subtitle>
          <v-card-text>
            <p class="program-description">{{ program.description || 'No description provided.' }}</p>
            <v-chip size="x-small" variant="tonal" class="mt-3">{{ program.source === 'manual' ? 'User entered' : program.source }}</v-chip>
          </v-card-text>
          <v-card-actions><span class="text-button text-primary">Open report <v-icon icon="mdi-arrow-right" size="small" /></span></v-card-actions>
        </v-card>
      </v-col>
    </v-row>
    <p v-if="items.length" class="text-caption text-medium-emphasis mt-3">{{ total }} program{{ total === 1 ? '' : 's' }}</p>

    <v-dialog v-model="dialog" max-width="620" persistent>
      <v-card>
        <v-card-title>Add government program</v-card-title>
        <v-card-text>
          <v-alert v-if="saveError" type="error" variant="tonal" class="mb-3">{{ saveError }}</v-alert>
          <v-form ref="form" @submit.prevent="save">
            <v-text-field v-model="draft.name" label="Program name" :rules="nameRules" maxlength="160" counter autofocus required />
            <v-text-field v-model="draft.agency" label="Agency" maxlength="160" />
            <v-text-field v-model="draft.program_code" label="Program code" maxlength="80" hint="Optional government identifier" />
            <v-textarea v-model="draft.description" label="Description" maxlength="2000" counter rows="3" />
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" :disabled="saving" @click="close">Cancel</v-btn>
          <v-btn color="primary" variant="flat" :loading="saving" :disabled="saving" @click="save">Save program</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <v-snackbar v-model="created">Program created successfully.</v-snackbar>
  </v-container>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { api, qs, type Program, type ProgramCreate, type ProgramListResponse } from '../api/client'

const q = ref(''); const items = ref<Program[]>([]); const total = ref(0)
const loading = ref(false); const loadError = ref(''); const dialog = ref(false)
const saving = ref(false); const saveError = ref(''); const created = ref(false); const form = ref()
let loadVersion = 0
const draft = reactive<ProgramCreate>({ name: '', agency: '', program_code: '', description: '' })
const nameRules = [(value: string) => value.trim().length >= 2 || 'Enter a program name with at least 2 characters.']

async function load() {
  const version = ++loadVersion
  loading.value = true; loadError.value = ''
  try {
    const result = await api.get<ProgramListResponse>(`/api/programs?${qs({ q: q.value, limit: 200 })}`)
    if (version === loadVersion) { items.value = result.items; total.value = result.total }
  } catch { if (version === loadVersion) loadError.value = 'Programs could not be loaded.' }
  finally { if (version === loadVersion) loading.value = false }
}
function close() { dialog.value = false; saveError.value = '' }
async function save() {
  const validation = await form.value?.validate()
  if (!validation?.valid) return
  saving.value = true; saveError.value = ''
  try {
    await api.post<Program>('/api/programs', draft)
    Object.assign(draft, { name: '', agency: '', program_code: '', description: '' })
    dialog.value = false; created.value = true; q.value = ''; await load()
  } catch (error: any) {
    saveError.value = error.message?.split(': ').slice(1).join(': ') || 'Program could not be saved.'
  } finally { saving.value = false }
}
let timer: ReturnType<typeof setTimeout>
watch(q, () => { clearTimeout(timer); timer = setTimeout(load, 250) })
onMounted(load)
</script>

<style scoped>
.program-description { min-height: 3em; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
</style>