<template>
  <v-dialog :model-value="modelValue" max-width="760" scrollable @update:model-value="$emit('update:modelValue', $event)">
    <v-card>
      <v-card-title class="d-flex align-center ga-2">
        <v-icon icon="mdi-help-circle-outline" size="20" />
        <span class="text-subtitle-1">Using Illuminate</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="$emit('update:modelValue', false)" />
      </v-card-title>
      <v-card-text class="help">
        <p class="lede">
          Illuminate maps defence programs to the companies, people, places and documents behind
          them. Ask it questions in plain language; read the answer on the graph.
        </p>

        <section>
          <h3><v-icon icon="mdi-chat-outline" size="16" /> Ask the graph</h3>
          <p>
            The panel on the right is the main way to work. Questions are answered against the graph
            currently on screen, so “the program” means whatever the focus picker is showing. An
            answer can restyle the canvas — highlighting a set of suppliers, colouring by risk — and
            every Cypher statement it ran is listed under the reply for you to check.
          </p>
          <p class="aside">Drag the divider to give the conversation more room, or double-click it to reset.</p>
        </section>

        <section>
          <h3><v-icon icon="mdi-cursor-default-click-outline" size="16" /> Work the canvas</h3>
          <dl>
            <dt>Click</dt><dd>a node or an edge to read its properties in the card on the right.</dd>
            <dt>Double-click</dt><dd>a company or person to pull in its neighbours.</dd>
            <dt>Search</dt><dd>by name, UEI or CAGE; a hit that is not on the canvas is fetched in.</dd>
            <dt>Focus</dt><dd>narrows everything to one program and its supply chain. Everything shows them all.</dd>
            <dt>Layers</dt><dd>chooses which kinds of node are drawn — people, countries, documents, claims.</dd>
            <dt>Canvas</dt><dd>fits, re-lays out, or clears the view and any styling the chat applied.</dd>
          </dl>
        </section>

        <section>
          <h3><v-icon icon="mdi-shield-alert-outline" size="16" /> Read a risk score</h3>
          <p>
            Companies and people are graded across seven dimensions. The card shows how much of the
            model actually returned data — a score built on two dimensions is not the same claim as
            one built on seven, and thin coverage is called out in words. Click any dimension to
            light up the nodes and edges it was computed from: a score you cannot walk back to its
            evidence is only an assertion.
          </p>
        </section>

        <section>
          <h3><v-icon icon="mdi-source-branch" size="16" /> Where the data came from</h3>
          <p>
            Every node and edge carries its source, when it was retrieved, and how it was derived.
            <strong>Enrich</strong> sends a company off to gather more; <strong>Find suppliers</strong>
            searches federal award records for a program; <strong>Report</strong> generates a document — a supply-chain
            risk assessment for a program, a vendor profile for a company — and keeps it in the graph, on the
            Reports tab, where it can be regenerated once the graph has moved on.
            Anything badged <strong>SIM</strong> is scenario material for analysis — not an allegation
            and not a verified finding.
          </p>
        </section>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="tonal" @click="$emit('update:modelValue', false)">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
<script setup lang="ts">
defineProps<{ modelValue: boolean }>()
defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()
</script>
<style scoped>
.help { font-size: 13.5px; line-height: 1.55; }
.lede { font-size: 14px; margin-bottom: 4px; }
section { margin-top: 18px; }
h3 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; opacity: .7; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
p { margin-bottom: 6px; }
.aside { opacity: .65; font-size: 12.5px; }
dl { display: grid; grid-template-columns: 110px 1fr; gap: 4px 10px; margin: 0; }
dt { font-weight: 600; }
dd { margin: 0; }
</style>
