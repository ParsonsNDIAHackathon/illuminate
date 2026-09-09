<template>
  <g class="transport-reference">
    <g v-for="corridor in transport.visible" :key="corridor.id" :class="['corridor', corridor.mode]" tabindex="0" role="button"
       :aria-label="`${corridor.name}, ${corridor.mode === 'truck' ? 'Interstate highway' : 'rail'} reference corridor`"
       @pointerdown.stop @click.stop="transport.selectedId = corridor.id" @keydown.enter.prevent="transport.selectedId = corridor.id" @keydown.space.prevent="transport.selectedId = corridor.id">
      <title>{{ corridor.name }} · {{ corridor.stops[0] }} to {{ corridor.stops.at(-1) }} · generalized reference</title>
      <path :d="shippingPath(corridor.points)" class="hit" />
      <path :d="shippingPath(corridor.points)" class="line" />
    </g>
  </g>
</template>
<script setup lang="ts">
import { useTransport } from '../stores/transport'
import { shippingPath } from '../shippingMap'
const transport = useTransport()
</script>
<style scoped>
.corridor { cursor:pointer; outline:none; }.line { fill:none; stroke:#59c8f0; stroke-width:2; vector-effect:non-scaling-stroke; pointer-events:none; }.rail .line { stroke:#ffb76c; stroke-width:2.5; stroke-dasharray:10 4; }.hit { fill:none; stroke:transparent; stroke-width:9; vector-effect:non-scaling-stroke; }.corridor:focus .line,.corridor:hover .line { stroke:white; stroke-width:3; }
</style>
