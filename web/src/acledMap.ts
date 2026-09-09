export type AcledPeriod = '7d' | '1m' | '3m' | '12m'
export interface AcledArea {
  id: string; country: string; name: string; latitude: number | null; longitude: number | null; sources: number[]
  periods: Record<string, Record<string, number[]>>
}
export interface AcledSnapshot {
  source: string; snapshot: string; through: string
  windows: Record<string, { after: string; through: string }>
  sources: { filename: string; through: string; sha256: string }[]
  places: AcledArea[]
}

/** Each row is a disjoint area/event-type aggregate; never mix in country summaries. */
export function acledPlaces(data: AcledSnapshot | null, period: AcledPeriod, eventType = '', country = '') {
  return (data?.places || []).filter(p => !country || p.country === country).map(p => {
    const breakdown = Object.entries(p.periods[period] || {})
      .filter(([type]) => !eventType || type === eventType)
      .map(([type, counts]) => ({ type, events: counts[0]!, fatalities: counts[1]! }))
    return { ...p, breakdown, events: breakdown.reduce((n, r) => n + r.events, 0),
      fatalities: breakdown.reduce((n, r) => n + r.fatalities, 0) }
  }).filter(p => p.events > 0 || p.fatalities > 0)
    .sort((a, b) => b.events - a.events || a.id.localeCompare(b.id))
}
