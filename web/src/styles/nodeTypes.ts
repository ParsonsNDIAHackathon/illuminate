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

/** Glyph geometry on a 24×24 grid, stroked (never filled) so `iconFor` can draw it twice. */
const GLYPHS: Record<NodeType, string> = {
  // a target: the thing a supply chain aims at
  Program: '<circle cx="12" cy="12" r="8.2"/><circle cx="12" cy="12" r="3.2"/>',
  // a building
  Organization: '<path d="M4.5 20.5V5.5a1.5 1.5 0 0 1 1.5-1.5h6a1.5 1.5 0 0 1 1.5 1.5v15"/><path d="M13.5 20.5v-9h4a1.5 1.5 0 0 1 1.5 1.5v7.5"/><path d="M3 20.5h18"/><path d="M7.5 8.2h3M7.5 12h3M7.5 15.8h3"/>',
  // head and shoulders
  Person: '<circle cx="12" cy="8" r="3.8"/><path d="M5 20.5v-.5a7 7 0 0 1 14 0v.5"/>',
  // a grid of tiles
  Category: '<path d="M4 4.5h6v6H4zM14 4.5h6v6h-6zM4 13.5h6v6H4zM14 13.5h6v6h-6z"/>',
  // a map pin
  Location: '<path d="M19.5 10.2c0 5.6-7.5 11.3-7.5 11.3s-7.5-5.7-7.5-11.3a7.5 7.5 0 0 1 15 0z"/><circle cx="12" cy="10.2" r="2.8"/>',
  // a page with a folded corner
  Artifact: '<path d="M13.5 3.2H7A2 2 0 0 0 5 5.2v13.6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.7z"/><path d="M13.5 3.2v5.5H19"/><path d="M8.8 13.5h6.4M8.8 17h4.2"/>',
  // a database cylinder: where a record came from, not a document
  Source: '<ellipse cx="12" cy="5.8" rx="7" ry="2.8"/><path d="M5 5.8v12.4c0 1.55 3.13 2.8 7 2.8s7-1.25 7-2.8V5.8"/><path d="M5 12c0 1.55 3.13 2.8 7 2.8s7-1.25 7-2.8"/>',
  // a speech bubble: something asserted
  Claim: '<path d="M20.5 14.6a2 2 0 0 1-2 2H8.2L4 20.8V5.4a2 2 0 0 1 2-2h12.5a2 2 0 0 1 2 2z"/>',
}

/** Order is the legend order. `shape` is a Cytoscape node shape.
 *
 *  `glyphScale` is the glyph's size as a share of the node box, and `glyphY` where it sits vertically
 *  (CSS background-position semantics: a share of the leftover space). Both vary by shape because the
 *  glyph is clipped to the shape: a rectangle fills its box and takes a large centred glyph, a diamond
 *  or a tag has to give ground at the corners, and a triangle is empty at the apex so its glyph is
 *  pushed down toward the wide base. Tuned against the smallest size each type is drawn at. */
export const NODE_TYPES: Record<NodeType, { label: string; shape: string; glyphScale: number; glyphY: number; fill: Record<Theme, string> }> = {
  Program:      { label: 'Program',      shape: 'round-rectangle', glyphScale: 58, glyphY: 50, fill: { light: '#6b8cba', dark: '#7f9fc6' } },
  Organization: { label: 'Organization', shape: 'ellipse',         glyphScale: 56, glyphY: 50, fill: { light: '#7b8794', dark: '#8e9aa8' } },
  Person:       { label: 'Person',       shape: 'diamond',         glyphScale: 52, glyphY: 50, fill: { light: '#6fa39a', dark: '#7fb0a7' } },
  Category:     { label: 'Category',     shape: 'hexagon',         glyphScale: 52, glyphY: 50, fill: { light: '#9a8cbf', dark: '#a89bcb' } },
  Location:     { label: 'Location',     shape: 'round-triangle',  glyphScale: 52, glyphY: 66, fill: { light: '#ab9b72', dark: '#b3a680' } },
  Artifact:     { label: 'Artifact',     shape: 'rectangle',       glyphScale: 58, glyphY: 50, fill: { light: '#9a9a94', dark: '#a3a39d' } },
  Source:       { label: 'Source',       shape: 'barrel',          glyphScale: 54, glyphY: 50, fill: { light: '#7da3bd', dark: '#8bb0c8' } },
  Claim:        { label: 'Claim',        shape: 'tag',             glyphScale: 48, glyphY: 50, fill: { light: '#bd8da6', dark: '#c69bb2' } },
}

// A Cytoscape background image cannot be recoloured by a selector, so the glyph colours are baked in.
// The disc underneath is not knowable up front — a style op repaints it anything from #facc15 to
// #15803d — so each glyph is stroked twice, a pale halo under dark ink. That is the same trick the
// node labels use (text-outline-width), and it makes one cached image legible on every fill, in both
// themes, which is why iconFor takes no theme.
const GLYPH_INK = '#14181e'
const GLYPH_HALO = '#f8fafc'
const iconCache = new Map<NodeType, string>()

/** A `data:` URI of the type's glyph, for a `background-image`. Cached: eight images for the whole canvas. */
export function iconForType(type: NodeType): string {
  const cached = iconCache.get(type)
  if (cached) return cached
  const pass = (stroke: string, width: number) =>
    `<g fill="none" stroke="${stroke}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round">${GLYPHS[type]}</g>`
  // width/height as well as viewBox: without them Firefox renders the image at zero size.
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">${pass(GLYPH_HALO, 4.2)}${pass(GLYPH_INK, 1.9)}</svg>`
  const uri = `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
  iconCache.set(type, uri)
  return uri
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
export function iconFor(n: Pick<GNode, 'label' | 'layer' | 'props'>): string { return iconForType(nodeType(n)) }
/** Glyph box as a Cytoscape percentage string, e.g. "52%". */
export function glyphScaleFor(n: Pick<GNode, 'label' | 'layer' | 'props'>): string { return `${NODE_TYPES[nodeType(n)].glyphScale}%` }
export function glyphYFor(n: Pick<GNode, 'label' | 'layer' | 'props'>): string { return `${NODE_TYPES[nodeType(n)].glyphY}%` }
