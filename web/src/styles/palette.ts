// Mirrors api/illuminate/styles.py. Names, never hex, cross the wire.
export const PALETTE: Record<string, { light: string; dark: string }> = {
  purple: { light: '#7c3aed', dark: '#a78bfa' },
  yellow: { light: '#ca8a04', dark: '#facc15' },
  teal: { light: '#0f766e', dark: '#2dd4bf' },
  orange: { light: '#ea580c', dark: '#fb923c' },
  red: { light: '#dc2626', dark: '#f87171' },
  green: { light: '#15803d', dark: '#4ade80' },
  blue: { light: '#1d4ed8', dark: '#60a5fa' },
  pink: { light: '#be185d', dark: '#f472b6' },
  brown: { light: '#92400e', dark: '#d6a26b' },
  neutral: { light: '#6b7280', dark: '#9ca3af' },
}
export const SWATCHES = Object.keys(PALETTE)

export function resolveSwatch(name: string | null | undefined, theme: 'light' | 'dark'): string {
  const n = (name || '').toLowerCase().trim()
  if (!PALETTE[n]) { if (n) console.warn(`[styles] unknown swatch "${n}" → neutral`); return PALETTE.neutral[theme] }
  return PALETTE[n][theme]
}

// Base colours per node label, theme-aware
export const LABEL_COLORS: Record<string, { light: string; dark: string }> = {
  Entity: { light: '#334155', dark: '#cbd5e1' },
  Program: { light: '#1d4ed8', dark: '#60a5fa' },
  Person: { light: '#0f766e', dark: '#2dd4bf' },
  Category: { light: '#7c3aed', dark: '#a78bfa' },
  Location: { light: '#92400e', dark: '#d6a26b' },
  Artifact: { light: '#6b7280', dark: '#9ca3af' },
  Source: { light: '#0369a1', dark: '#7dd3fc' },   // an Artifact on the sources layer (registry entry / source record)
  Claim: { light: '#be185d', dark: '#f472b6' },
}
