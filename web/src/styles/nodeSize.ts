// How big a node is drawn at rest.
//
// Suppliers are sized by tier: a tier-1 prime is the largest organisation on the canvas, a tier-2
// sub-awardee smaller, and so on down the chain, so the shape of the supply base reads at a glance
// without the edge labels. Tier is a property of the SUPPLIES edge, not the entity (schema.py), and
// a supplier can sit at several tiers for different consumers, so a node takes its *lowest* tier —
// the closest it gets to a program — over every SUPPLIES edge currently on the canvas.
import type { GEdge, GNode } from '../stores/graph'

/** Diameter in px by supplier tier; anything deeper than the last entry takes the last entry. Order is the legend order. */
export const TIER_SIZES: { tier: number; size: number }[] = [
  { tier: 1, size: 46 },
  { tier: 2, size: 36 },
  { tier: 3, size: 30 },
  { tier: 4, size: 26 },
]
const PROGRAM_SIZE = 56
const ORG_SIZE = 32       // an organisation with no supply edge on the canvas: a parent, an owner, a lone search result
const PERSON_SIZE = 26
const OTHER_SIZE = 22

export function tierSize(tier: number): number {
  const hit = TIER_SIZES.find(t => t.tier === tier) || TIER_SIZES[TIER_SIZES.length - 1]
  return hit.size
}

/** Lowest SUPPLIES tier per supplier id. An untiered edge straight into a program counts as tier 1. */
export function supplierTiers(edges: Pick<GEdge, 'source' | 'target' | 'type' | 'props'>[], nodes: Pick<GNode, 'id' | 'props'>[]): Map<string, number> {
  const programs = new Set(nodes.filter(n => n.props?.kind === 'program').map(n => n.id))
  const tiers = new Map<string, number>()
  for (const e of edges) {
    if (e.type !== 'SUPPLIES') continue
    const raw = Number(e.props?.tier)
    const tier = Number.isFinite(raw) && raw >= 1 ? raw : programs.has(e.target) ? 1 : NaN
    if (!Number.isFinite(tier)) continue
    const prev = tiers.get(e.source)
    if (prev === undefined || tier < prev) tiers.set(e.source, tier)
  }
  return tiers
}

export function nodeSize(n: Pick<GNode, 'label' | 'props'>, tier?: number): number {
  if (n.props?.kind === 'program') return PROGRAM_SIZE
  if (n.label === 'Entity') return tier ? tierSize(tier) : ORG_SIZE
  if (n.label === 'Person') return PERSON_SIZE
  return OTHER_SIZE
}
