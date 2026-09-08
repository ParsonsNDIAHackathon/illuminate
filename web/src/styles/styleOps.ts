import type { Core } from 'cytoscape'
import { resolveSwatch } from './palette.ts'

export interface StyleSpec { fill?: string; stroke?: string; badge?: string; size?: 'sm' | 'md' | 'lg' | 'xl'; shape?: string; dashed?: boolean }
export interface StyleOp { op: 'clear' | 'set' | 'dim' | 'highlight' | 'hide'; ids?: string[]; scope?: 'all' | 'nodes' | 'edges'; style?: StyleSpec; label?: string }
export interface LegendItem { swatch: string; label: string; count: number }

const SIZE: Record<string, number> = { sm: 22, md: 32, lg: 44, xl: 58 }
const STYLE_KEYS = ['op-fill', 'op-stroke', 'op-badge', 'op-size', 'op-shape', 'op-dashed', 'op-dim', 'op-hide', 'op-highlight']

/** Maps ops onto element data + classes; idempotent per op list. */
export function applyStyleOps(cy: Core, ops: StyleOp[], theme: 'light' | 'dark') {
  for (const op of ops) {
    if (op.op === 'clear') { clearStyleOps(cy, op.scope); continue }
    const eles = cy.collection(op.ids?.map(id => cy.getElementById(id)).filter(e => e && e.nonempty()) as any)
    if (op.op === 'dim') { eles.addClass('op-dim'); continue }
    if (op.op === 'hide') { eles.addClass('op-hide'); continue }
    const st = op.style || {}
    eles.forEach(e => {
      if (st.fill) e.data('opFill', resolveSwatch(st.fill, theme)), e.addClass('op-fill')
      if (st.stroke) e.data('opStroke', resolveSwatch(st.stroke, theme)), e.addClass('op-stroke')
      if (st.badge) e.data('opBadge', st.badge), e.addClass('op-badge')
      if (st.size) e.data('opSize', SIZE[st.size] || 32), e.addClass('op-size')
      if (st.shape) e.data('opShape', st.shape), e.addClass('op-shape')
      if (st.dashed) e.addClass('op-dashed')
      if (op.op === 'highlight') e.addClass('op-highlight')
      e.removeClass('op-dim')
    })
  }
}

export function clearStyleOps(cy: Core, scope: 'all' | 'nodes' | 'edges' = 'all') {
  const eles = scope === 'nodes' ? cy.nodes() : scope === 'edges' ? cy.edges() : cy.elements()
  eles.removeClass(STYLE_KEYS.join(' '))
  eles.forEach(e => { for (const k of ['opFill', 'opStroke', 'opBadge', 'opSize', 'opShape']) e.removeData(k) })
}

/** Legend derived from ops, never authored. */
export function deriveLegend(ops: StyleOp[]): LegendItem[] {
  const buckets = new Map<string, LegendItem>()
  for (const op of ops) {
    if (op.op === 'clear') { buckets.clear(); continue }
    if ((op.op !== 'set' && op.op !== 'highlight') || !op.style) continue
    const sw = (op.style.fill || op.style.stroke || 'neutral').toLowerCase()
    const label = op.label || op.style.badge || sw
    const key = `${sw}|${label}`
    const cur = buckets.get(key) || { swatch: sw, label, count: 0 }
    cur.count += op.ids?.length || 0
    buckets.set(key, cur)
  }
  return [...buckets.values()]
}

/** Re-resolve swatches after a theme switch. */
export function rethemeStyleOps(cy: Core, ops: StyleOp[], theme: 'light' | 'dark') { clearStyleOps(cy); applyStyleOps(cy, ops, theme) }
