// How a risk score is drawn. Mirrors api/illuminate/risk.py — bands, thresholds and the
// severity vocabulary all come from there, and the names, never hex, are what cross the wire.
//
// Two rules the visual encoding has to keep:
//
// 1. **Unscored is not low.** A node the scorer could say nothing about gets no halo, no
//    colour and the word "unscored" — never the reassuring end of a green-to-red ramp. The
//    whole model refuses to impute zeros and the canvas must not undo that.
// 2. **Confidence rides with the score.** A 100 built on two of seven dimensions is a real
//    finding and a thin one; wherever the number is shown, how much of the model answered
//    is shown next to it.
// Explicit extension: this module is covered by tests/risk.test.ts, which runs under node's
// type stripping and resolves imports the way node does, not the way vite does.
import { PALETTE } from './palette.ts'
import type { Theme } from './nodeTypes'

export type RiskBand = 'low' | 'elevated' | 'high' | 'severe'
export type Severity = 'clear' | 'low' | 'medium' | 'high'

/** Bands in ascending order of concern, with the score floor each begins at (risk.BANDS). */
export const RISK_BANDS: { band: RiskBand; floor: number; label: string; swatch: keyof typeof PALETTE }[] = [
  { band: 'severe', floor: 75, label: 'Severe', swatch: 'red' },
  { band: 'high', floor: 50, label: 'High', swatch: 'orange' },
  { band: 'elevated', floor: 25, label: 'Elevated', swatch: 'yellow' },
  // Neutral, not green: a low score often means "screened clear on the little we asked",
  // which is not the same as safe and should not be painted as an all-clear.
  { band: 'low', floor: 0, label: 'Low', swatch: 'neutral' },
]

const BY_BAND = new Map(RISK_BANDS.map(b => [b.band, b]))

export function bandOf(score: number | null | undefined): RiskBand | null {
  if (score == null) return null
  return (RISK_BANDS.find(b => score >= b.floor) || RISK_BANDS[RISK_BANDS.length - 1]).band
}

export function bandLabel(band: string | null | undefined): string {
  return BY_BAND.get(band as RiskBand)?.label ?? 'Unscored'
}

export function bandColor(band: string | null | undefined, theme: Theme): string | null {
  const hit = BY_BAND.get(band as RiskBand)
  return hit ? PALETTE[hit.swatch][theme] : null
}

/** Vuetify colour token for a band chip. Unscored deliberately has none. */
export function bandChip(band: string | null | undefined): string | undefined {
  return ({ severe: 'error', high: 'warning', elevated: 'secondary', low: undefined } as Record<string, string | undefined>)[band || '']
}

/** Severity of one dimension, in the same vocabulary report.py and risk.py both grade in. */
export function sevColor(s: string | null | undefined): string | undefined {
  return ({ high: 'error', medium: 'warning', low: 'secondary', clear: 'success' } as Record<string, string>)[s || '']
}

export function sevIcon(s: string | null | undefined): string {
  return ({ high: 'mdi-alert-octagon', medium: 'mdi-alert', low: 'mdi-information-outline', clear: 'mdi-check-circle-outline' } as Record<string, string>)[s || '']
    || 'mdi-help-circle-outline'
}

/** "96 · severe" / "unscored". The one place the null case is worded. */
export function scoreLabel(score: number | null | undefined, band?: string | null): string {
  if (score == null) return 'unscored'
  return `${score} · ${bandLabel(band ?? bandOf(score)).toLowerCase()}`
}

/** How thin a score is, in words. Thresholds match the note risk.py writes. */
export function confidenceNote(confidence: number | null | undefined, scored?: number, requested?: number): string {
  if (confidence == null) return ''
  const of = scored != null && requested != null ? ` (${scored} of ${requested} dimensions)` : ''
  if (confidence < 30) return `Very thin — ${confidence}% of the model answered${of}`
  if (confidence < 60) return `Thin — ${confidence}% of the model answered${of}`
  return `${confidence}% of the model answered${of}`
}

export function isThin(confidence: number | null | undefined): boolean {
  return confidence != null && confidence < 60
}

/** The halo a scored node wears on the canvas: drawn *under* the node, so it never competes
 *  with the border, which already carries root, selection, simulated and style-op state. */
export function haloFor(band: string | null | undefined, theme: Theme): { color: string; padding: number; opacity: number } | null {
  const color = bandColor(band, theme)
  if (!color || band === 'low') return null   // only concern is worth ink
  const padding = band === 'severe' ? 9 : band === 'high' ? 7 : 5
  return { color, padding, opacity: band === 'severe' ? 0.42 : band === 'high' ? 0.34 : 0.26 }
}
