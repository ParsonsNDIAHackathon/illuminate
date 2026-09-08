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

// Node fills at rest live in nodeTypes.ts: muted on purpose, so these swatches read as highlights over them.
