<template>
  <g v-if="shipping.visible" class="shipping-layer">
    <g v-for="item in shipping.routes" :key="item.route.id" class="shipping-route" :class="[item.route.status, { selected: shipping.selectedId === item.route.id }]"
       tabindex="0" role="button" :aria-label="`${item.route.name}, ${item.route.status}. ${item.supplier.name} to ${item.customer.name}`"
       @pointerdown.stop @click.stop="shipping.select(item.route.id)" @keydown.enter.prevent="shipping.select(item.route.id)" @keydown.space.prevent="shipping.select(item.route.id)">
      <title>{{ item.route.name }} · {{ item.route.status }} · {{ item.route.goods }}</title>
      <path :d="routePath(item.route, shipping.catalog.ports)" class="route-hit" />
      <path v-for="(segment, i) in item.route.segments" :key="i" :d="segmentPath(segment, shipping.catalog.ports)" :class="['route-line', segment.mode || 'ocean']" />
    </g>
    <g v-for="port in shipping.ports" :key="port.id" :transform="`translate(${(port.longitude + 180) * 3},${(90 - port.latitude) * 3})`"
       class="shipping-port" :class="{ selected: shipping.port === port.id }" role="button" tabindex="0" :aria-label="`${port.name} ${port.kind === 'port' || !port.kind ? 'port' : 'hub'}, ${count(port.id)} route records`"
       @pointerdown.stop @click.stop="pickPort(port.id)" @keydown.enter.prevent="pickPort(port.id)" @keydown.space.prevent="pickPort(port.id)">
      <title>{{ port.name }} · {{ count(port.id) }} route records · approximate connection position</title>
      <rect v-if="!port.kind || port.kind === 'port'" :x="-6 / scale" :y="-6 / scale" :width="12 / scale" :height="12 / scale" :rx="2 / scale" />
      <circle v-else :r="6 / scale" />
      <text v-if="showLabels || shipping.port === port.id" :y="-12 / scale" :font-size="11 / scale" text-anchor="middle">{{ port.name }}</text>
    </g>
  </g>
</template>
<script setup lang="ts">
import { useShipping } from '../stores/shipping'
import { routePath, usesPort, segmentPath } from '../shippingMap'
defineProps<{ scale: number; showLabels: boolean }>()
const shipping = useShipping()
function count(id: string) { return shipping.filtered.filter(x => usesPort(x.route, id)).length }
function pickPort(id: string) { shipping.port = shipping.port === id ? '' : id; shipping.selectedId = '' }
</script>
<style scoped>
.shipping-route,.shipping-port { cursor:pointer; outline:none; }
.route-line { fill:none; stroke:#a7b8ff; stroke-width:2; vector-effect:non-scaling-stroke; pointer-events:none; }
.route-hit { fill:none; stroke:transparent; stroke-width:14; vector-effect:non-scaling-stroke; }
.inferred .route-line { stroke:#ffca80; stroke-dasharray:8 5; }
.illustrative .route-line { stroke:#c7a7ff; stroke-dasharray:2 6; }
.confirmed .route-line { stroke:#65dfcf; }
.route-line.truck { stroke-width:3; }.route-line.rail { stroke-width:4; }
.selected .route-line,.shipping-route:focus .route-line { stroke:#fff; stroke-width:3.5; }
.shipping-port rect,.shipping-port circle { fill:#c7a7ff; stroke:#102b38; stroke-width:2; vector-effect:non-scaling-stroke; }
.shipping-port.selected rect,.shipping-port:focus rect,.shipping-port.selected circle,.shipping-port:focus circle { stroke:white; }
.shipping-port text { fill:#f0e8ff; paint-order:stroke; stroke:#102b38; stroke-width:3; vector-effect:non-scaling-stroke; pointer-events:none; }
</style>
