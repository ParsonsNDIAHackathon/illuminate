<template>
  <v-dialog :model-value="!!req" persistent max-width="760">
    <v-card v-if="req">
      <v-card-title class="d-flex align-center ga-2">
        <v-icon icon="mdi-alert" color="warning" />
        <span>Permission required</span>
        <v-chip size="x-small" :color="req.classification === 'DESTRUCTIVE' ? 'error' : 'warning'" variant="tonal">{{ req.classification }}</v-chip>
        <v-chip size="x-small" variant="outlined">from {{ req.source }}<span v-if="req.tool"> · {{ req.tool }}</span></v-chip>
        <v-spacer />
        <span v-if="pending.length > 1" class="text-caption">{{ pending.length }} pending</span>
      </v-card-title>
      <v-card-text>
        <p v-if="req.rationale" class="mb-2">{{ req.rationale }}</p>
        <p class="text-body-2 mb-2">This will modify the graph.</p>
        <v-textarea v-if="editing" v-model="edited" rows="6" variant="outlined" class="mono" hide-details />
        <CypherBlock v-else :statement="req.statement" :params="req.params" :classification="req.classification" />
        <div class="d-flex flex-wrap ga-2 my-3">
          <v-chip variant="tonal" color="success">creates {{ c.nodes_created || 0 }} node{{ (c.nodes_created||0) === 1 ? '' : 's' }}</v-chip>
          <v-chip variant="tonal" color="success">creates {{ c.relationships_created || 0 }} relationship{{ (c.relationships_created||0) === 1 ? '' : 's' }}</v-chip>
          <v-chip variant="tonal" :color="(c.properties_set||0) ? 'warning' : undefined">sets {{ c.properties_set || 0 }} propert{{ (c.properties_set||0) === 1 ? 'y' : 'ies' }}</v-chip>
          <v-chip variant="tonal" :color="deleted ? 'error' : undefined">deletes {{ deleted }}</v-chip>
        </div>
        <div class="text-caption" style="opacity:.7">Counts come from a real execution inside a rolled-back transaction — not an estimate.</div>
        <v-alert v-if="req.preview.error" type="error" variant="tonal" density="compact" class="mt-2">{{ req.preview.error }}</v-alert>
        <v-alert v-if="error" type="warning" variant="tonal" density="compact" class="mt-2">{{ error }}</v-alert>
        <v-checkbox v-if="req.classification === 'DESTRUCTIVE'" v-model="ack" density="compact" hide-details :label="`I acknowledge ${deleted} element(s) will be deleted`" class="mt-2" />
      </v-card-text>
      <v-card-actions>
        <v-btn color="primary" variant="flat" :loading="busy" @click="approve(false)">Approve once</v-btn>
        <v-btn variant="tonal" :loading="busy" @click="approve(true)" title="Auto-approve this statement shape for the rest of the session">Approve this shape for the session</v-btn>
        <v-btn variant="text" @click="editing ? (editing = false) : startEdit()">{{ editing ? 'Cancel edit' : 'Edit query' }}</v-btn>
        <v-spacer />
        <v-btn color="error" variant="tonal" :loading="busy" @click="refuse">Refuse</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { usePermissions } from '../stores/permissions'
import CypherBlock from './CypherBlock.vue'
const perms = usePermissions()
const pending = computed(() => perms.pending)
const req = computed(() => perms.current)
const c = computed(() => req.value?.preview?.counters || {})
const deleted = computed(() => (c.value.nodes_deleted || 0) + (c.value.relationships_deleted || 0))
const editing = ref(false); const edited = ref(''); const ack = ref(false); const busy = ref(false); const error = ref('')
watch(req, () => { editing.value = false; ack.value = false; error.value = '' })
function startEdit() { edited.value = req.value!.statement; editing.value = true }
async function approve(remember: boolean) {
  if (!req.value) return
  busy.value = true; error.value = ''
  try {
    const d = await perms.approve(req.value.id, { edited_statement: editing.value ? edited.value : undefined, remember_shape: remember, acknowledge_count: req.value.classification === 'DESTRUCTIVE' ? (ack.value ? deleted.value : undefined) : undefined })
    if (d.status === 'pending') { error.value = d.reason; if (editing.value) await perms.load() }
    else perms.resolve({ ...req.value, status: d.status })
  } catch (e: any) { error.value = e.message } finally { busy.value = false }
}
async function refuse() {
  if (!req.value) return
  busy.value = true
  try { await perms.refuse(req.value.id, 'refused in UI'); perms.resolve({ ...req.value, status: 'refused' }) } finally { busy.value = false }
}
</script>
<style scoped>
.mono :deep(textarea) { font-family: ui-monospace, monospace; font-size: 12px; }
@media (max-width: 767px) {
  :deep(.v-card-actions .v-btn) { flex: 1 1 210px; }
  :deep(.v-card-actions .v-spacer) { display: none; }
}
</style>
