// What kind of thing a node is, and how the canvas draws that kind at rest.
//
// The fills are deliberately muted: mid-lightness, low chroma, and none of them a PALETTE swatch.
// Type colour is the quiet ground; user highlighting (style ops, selection, search matches, the
// root ring) is the saturated figure on top of it and must never have to compete with it.
import type { GNode } from '../stores/graph'

export type Theme = 'light' | 'dark'
export type NodeType = 'Organization' | 'Program' | 'Person' | 'Category' | 'Location' | 'Artifact' | 'Source' | 'Claim'

/** Artifact kinds that point at where data came from rather than being a document. Mirrors schema.SOURCE_KINDS. */
export const SOURCE_KINDS = new Set(['record', 'registry'])

/** Order is the legend order. `shape` is a Cytoscape node shape. */
export const NODE_TYPES: Record<NodeType, { label: string; shape: string; fill: Record<Theme, string> }> = {
  Program:      { label: 'Program',      shape: 'round-rectangle', fill: { light: '#6b8cba', dark: '#7f9fc6' } },
  Organization: { label: 'Organization', shape: 'ellipse',         fill: { light: '#7b8794', dark: '#8e9aa8' } },
  Person:       { label: 'Person',       shape: 'diamond',         fill: { light: '#6fa39a', dark: '#7fb0a7' } },
  Category:     { label: 'Category',     shape: 'hexagon',         fill: { light: '#9a8cbf', dark: '#a89bcb' } },
  Location:     { label: 'Location',     shape: 'round-triangle',  fill: { light: '#ab9b72', dark: '#b3a680' } },
  Artifact:     { label: 'Artifact',     shape: 'rectangle',       fill: { light: '#9a9a94', dark: '#a3a39d' } },
  Source:       { label: 'Source',       shape: 'barrel',          fill: { light: '#7da3bd', dark: '#8bb0c8' } },
  Claim:        { label: 'Claim',        shape: 'tag',             fill: { light: '#bd8da6', dark: '#c69bb2' } },
}

/** The canvas layer a node belongs to, or null for entities, which are always drawn.
 *  The server names it (graphio.layer_of); the fallback mirrors that for nodes from a route that predates the field. */
export function layerOf(n: Pick<GNode, 'label' | 'layer' | 'props'>): string | null {
  if (n.layer !== undefined) return n.layer
  if (n.label === 'Artifact') return SOURCE_KINDS.has(n.props?.kind || 'record') ? 'sources' : 'artifacts'
  return ({ Person: 'people', Location: 'countries', Category: 'categories', Claim: 'claims' } as Record<string, string>)[n.label] || null
}

export function nodeType(n: Pick<GNode, 'label' | 'layer' | 'props'>): NodeType {
  if (n.label === 'Entity') return n.props?.kind === 'program' ? 'Program' : 'Organization'
  if (n.label === 'Artifact') return layerOf(n) === 'sources' ? 'Source' : 'Artifact'
  return (n.label in NODE_TYPES ? n.label : 'Organization') as NodeType
}

export function fillFor(n: Pick<GNode, 'label' | 'layer' | 'props'>, theme: Theme): string { return NODE_TYPES[nodeType(n)].fill[theme] }
export function shapeFor(n: Pick<GNode, 'label' | 'layer' | 'props'>): string { return NODE_TYPES[nodeType(n)].shape }

// Edges take the tint of the type they lead to, a shade darker on the light ground so a 1.4px line
// still shows. Same rule as the fills: quiet enough that a highlighted path is unmistakable.
const EDGE_TINTS: Record<string, Record<Theme, string>> = {
  supply:    { light: '#8a94a3', dark: '#6b7583' },
  control:   { light: '#b48660', dark: '#b58a66' },
  people:    { light: '#5f948b', dark: '#6f9e96' },
  category:  { light: '#8c7eb0', dark: '#978bb9' },
  place:     { light: '#9d8d65', dark: '#a39670' },
  evidence:  { light: '#a3a39d', dark: '#7c7c77' },
  claim:     { light: '#b07e97', dark: '#a9819a' },
}
const EDGE_FAMILY: Record<string, keyof typeof EDGE_TINTS> = {
  SUPPLIES: 'supply', OWNS: 'control', ULTIMATE_PARENT_OF: 'control', HELD_ROLE: 'people', BENEFICIAL_OWNER_OF: 'people',
  PROVIDES: 'category', SUBCATEGORY_OF: 'category', INCORPORATED_IN: 'place', OPERATES_IN: 'place', MANUFACTURES_IN: 'place', PARENT_SEATED_IN: 'place',
  MEMBER_OF: 'people', TRANSACTS_WITH: 'people', LOBBIES: 'people', DONATED_TO: 'people',
  EVIDENCES: 'evidence', ABOUT: 'evidence', ASSERTS: 'claim', TARGETS: 'claim',
}
export function edgeColor(type: string, theme: Theme): string { return EDGE_TINTS[EDGE_FAMILY[type] || 'supply'][theme] }
