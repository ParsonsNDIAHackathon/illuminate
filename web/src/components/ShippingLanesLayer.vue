<template>
  <g v-if="lanes.enabled" class="lanes-layer">
    <g v-for="lane in lanes.lanes" :key="lane.id" tabindex="0" role="button" :aria-label="`Established lane: ${lane.name}`"
       @pointerdown.stop @click.stop="lanes.selectedId = lane.id" @keydown.enter.prevent="lanes.selectedId = lane.id" @keydown.space.prevent="lanes.selectedId = lane.id">
      <title>{{ lane.name }} · {{ lane.service }} · Published {{ lane.published_at }} · Schematic path</title>
      <path :d="routePath(lane, lanes.catalog.ports)" class="hit" />
      <path :d="routePath(lane, lanes.catalog.ports)" class="lane" :class="{ selected: lanes.selectedId === lane.id }" />
    </g>
    <g v-for="port in lanes.ports" :key="port.id" :transform="`translate(${(port.longitude + 180) * 3},${(90 - port.latitude) * 3})`"
       tabindex="0" role="button" :aria-label="`${port.name} port: filter established lanes`"
       @pointerdown.stop @click.stop="pick(port.id)" @keydown.enter.prevent="pick(port.id)" @keydown.space.prevent="pick(port.id)">
      <title>{{ port.name }} · Established service connections</title>
      <rect :x="-5 / scale" :y="-5 / scale" :width="10 / scale" :height="10 / scale" />
      <text v-if="showLabels || lanes.port === port.id" :y="-10 / scale" :font-size="11 / scale" text-anchor="middle">{{ port.name }}</text>
    </g>
  </g>
</template>
<script setup lang="ts">
import { useShippingLanes } from '../stores/shippingLanes'
import { routePath } from '../shippingMap'
defineProps<{ scale: number; showLabels: boolean }>()
const lanes = useShippingLanes()
function pick(id: string) { lanes.port = lanes.port === id ? '' : id }
</script>
<style scoped>
g[role=button] { cursor:pointer; }
.lane { fill:none; stroke:#65dfcf; stroke-width:2; vector-effect:non-scaling-stroke; pointer-events:none; }
.hit { fill:none; stroke:transparent; stroke-width:12; vector-effect:non-scaling-stroke; }
.lane.selected,g:focus > .lane { stroke:white; stroke-width:4; }
rect { fill:#65dfcf; stroke:#102b38; stroke-width:1.5; vector-effect:non-scaling-stroke; }
text { fill:white; paint-order:stroke; stroke:#102b38; stroke-width:3; }
</style>
