// How big a node is drawn at rest.
//
// Suppliers are sized by tier: a tier-1 prime is the largest organisation on the canvas, a tier-2
// sub-awardee smaller, and so on down the chain, so the shape of the supply base reads at a glance
// without the edge labels. Tier is a property of the SUPPLIES edge, not the entity (schema.py), and
// a supplier can sit at several tiers for different consumers, so a node takes its *lowest* tier —
// the closest it gets to a program — over every SUPPLIES edge currently on the canvas.
//
// What kind of thing a node is stays in nodeTypes.ts; this module only says how big that kind draws.
import type { GEdge, GNode } from '../stores/graph'
import { nodeType, type NodeType } from './nodeTypes'

/** Diameter in px by supplier tier; anything deeper than the last entry takes the last entry. Order is the legend order. */
export const TIER_SIZES: { tier: number; size: number }[] = [
  { tier: 1, size: 46 },
  { tier: 2, size: 36 },
  { tier: 3, size: 30 },
  { tier: 4, size: 26 },
]

/** Size at rest per node type. Organizations use this only when no SUPPLIES edge on the canvas tiers them. */
const BASE_SIZE: Record<NodeType, number> = {
  Program: 56,
  Organization: 32,   // a parent, an owner, or a lone search result: nothing that places it in a supply chain
  Person: 26,
  Category: 22,
  Location: 22,
  Artifact: 22,
  Source: 22,
  Claim: 22,
  Report: 30,     // a deliverable, drawn a size up from the evidence it was written from
}

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

export function nodeSize(n: Pick<GNode, 'label' | 'layer' | 'props'>, tier?: number): number {
  const type = nodeType(n)
  if (type === 'Organization' && tier) return tierSize(tier)
  return BASE_SIZE[type]
}
