export type NewsArticle = { url: string; title: string; seendate: string; domain: string; language: string; provider?: string; providers?: string[]; publisher?: string; published_at?: string; locations?: NewsLocation[] }
export type NewsLocation = { code: string; name: string; latitude: number; longitude: number; country: string; precision: 'locality'; source: string; evidence: string }
type Country = { code: string; name: string; latitude: number; longitude: number }
const aliases: Record<string, string[]> = {
  US: ['United States', 'USA', 'U.S.', 'US'], CA: ['Canadian'], GB: ['United Kingdom', 'Britain', 'UK'],
  UA: ['Ukraine', 'Ukrainian'], RU: ['Russia', 'Russian'], CN: ['China', 'Chinese'],
  IL: ['Israel', 'Israeli'], PS: ['Palestine', 'Palestinian', 'Gaza'],
  IR: ['Iran', 'Iranian'], TW: ['Taiwan', 'Taiwanese'], NP: ['Nepalese', 'Nepali'], KR: ['South Korea'], KP: ['North Korea'],
}
type Region = Country & { country: string }
// Distinctive administrative names can place local headlines without guessing from
// the publisher. Ambiguous names (Georgia, Washington, Victoria, etc.) need a country.
const distinctiveRegions = new Set([
  'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut',
  'Delaware', 'Florida', 'Hawaii', 'Idaho', 'Illinois', 'Iowa', 'Kansas', 'Kentucky',
  'Louisiana', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi',
  'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire', 'New Jersey',
  'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma',
  'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
  'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'West Virginia', 'Wisconsin',
  'Wyoming', 'Ontario', 'Quebec', 'Québec', 'Alberta', 'British Columbia', 'Manitoba',
  'Saskatchewan', 'Nova Scotia', 'New Brunswick', 'Newfoundland and Labrador',
  'New South Wales', 'Queensland', 'Tasmania', 'Western Australia', 'South Australia',
])
function namePattern(name: string) {
  const escaped = [...name].map(char => '.*+?^$()[]{}|'.includes(char) || char.charCodeAt(0) === 92 ? String.fromCharCode(92) + char : char).join('')
  return new RegExp(String.raw`(?<![\p{L}])${escaped}(?![\p{L}])`, name.length === 2 ? 'u' : 'iu')
}
// Locations are headline mentions, not incident coordinates or publisher locations.
export function mapNews(articles: NewsArticle[], countries: Country[], regions: Region[] = []) {
  const countryPatterns = countries.map(country => ({ country, patterns: [country.name, ...(aliases[country.code] || [])]
    .filter(name => name.length >= 2).map(namePattern) }))
  const countryNames = new Map(countries.map(c => [c.code, c.name]))
  const regionPatterns = regions.filter(r => r.code && countryNames.has(r.country) && r.name.length >= 4)
    .map(region => ({ region, pattern: namePattern(region.name) }))
  const byPlace = new Map<string, Country & { precision?: 'locality'; articles: NewsArticle[] }>()
  const placed = new Set<string>()
  for (const article of articles) {
    const countryMatches = countryPatterns.filter(p => p.patterns.some(pattern => pattern.test(article.title))).map(p => p.country)
    const mentioned = new Set(countryMatches.map(c => c.code))
    const regionMatches = regionPatterns.filter(({region, pattern}) =>
      ((['US', 'CA', 'AU'].includes(region.country) && distinctiveRegions.has(region.name)) || mentioned.has(region.country))
      && pattern.test(article.title))
      // Prefer West Virginia over the contained name Virginia, for example.
      .filter((candidate, _, matches) => !matches.some(other => other.region.name !== candidate.region.name && other.region.name.includes(candidate.region.name)))
    const regionalCountries = new Set(regionMatches.map(p => p.region.country))
    const localities = (article.locations || []).filter(p => p.precision === 'locality'
      && Number.isFinite(p.latitude) && Math.abs(p.latitude) <= 90
      && Number.isFinite(p.longitude) && Math.abs(p.longitude) <= 180)
    const localCountries = new Set(localities.map(p => p.country))
    const matches = [...localities, ...countryMatches.filter(c => !regionalCountries.has(c.code) && !localCountries.has(c.code)),
      ...regionMatches.filter(({region}) => !localCountries.has(region.country)).map(({region}) => ({...region, name: `${region.name}, ${countryNames.get(region.country)}`}))]
    for (const place of matches) {
      if (!byPlace.has(place.code)) byPlace.set(place.code, { ...place, articles: [] })
      byPlace.get(place.code)!.articles.push(article)
      placed.add(article.url)
    }
  }
  const order = new Map([...countries, ...regions].map((place, i) => [place.code, i]))
  const places = [...byPlace.values()].sort((a, b) => (order.get(a.code) ?? 999999) - (order.get(b.code) ?? 999999))
  return { places, mapped: placed.size, unmapped: articles.filter(article => !placed.has(article.url)) }
}
export function newsDate(value: string) {
  return /^\d{8}T\d{6}Z$/.test(value) ? `${value.slice(0,4)}-${value.slice(4,6)}-${value.slice(6,8)} ${value.slice(9,11)}:${value.slice(11,13)} UTC` : value
}

/** Preview uses the artifact viewer without asserting a stored graph artifact. */
export function newsPreview(article: NewsArticle, locations: string[]) {
  return {
    artifact: { title: article.title, url: article.url, kind: 'news', source: article.providers?.join(' + ') || article.provider || 'GDELT' },
    summary: { sections: [{ title: 'News coverage', fields: [
      { label: 'Publisher', value: article.domain || 'Unknown' },
      { label: article.published_at ? 'Published' : 'Seen by GDELT', value: newsDate(article.published_at || article.seendate) || 'Unknown' },
      { label: 'Language', value: article.language || 'Unknown' },
      { label: 'Headline locations', value: locations.join(', ') || 'Unplaced' },
    ], note: 'Locations are inferred from headline mentions. Town/city markers use GeoNames locality coordinates, not verified incident coordinates; otherwise country or state/province centers are used. This search result has not been saved to the graph.' }] },
    raw: [{ match: `${article.provider || 'GDELT'} search result`, url: article.url, body: article }],
  }
}

export const NEWS_PROXIMITY_KM = 250
type Point = { latitude: number; longitude: number }
const radians = Math.PI / 180
const wrapLongitude = (value: number) => ((value + 180) % 360 + 360) % 360 - 180
function distanceKm(a: Point, b: Point) {
  const lat = (b.latitude - a.latitude) * radians
  const lon = wrapLongitude(b.longitude - a.longitude) * radians
  const h = Math.sin(lat / 2) ** 2 + Math.cos(a.latitude * radians) * Math.cos(b.latitude * radians) * Math.sin(lon / 2) ** 2
  return 6371 * 2 * Math.asin(Math.sqrt(Math.min(1, h)))
}
// Match the map's straight latitude/longitude segments, unwrapped across the
// dateline. Local kilometer projection finds the closest point on each segment.
function nearSegment(point: Point, a: Point, b: Point, radius: number) {
  const dx = wrapLongitude(b.longitude - a.longitude)
  const dy = b.latitude - a.latitude
  const cos = Math.cos(point.latitude * radians)
  const px = wrapLongitude(point.longitude - a.longitude)
  const py = point.latitude - a.latitude
  const length = (dx * cos) ** 2 + dy ** 2
  return [-360, 0, 360].some(shift => {
    const t = length ? Math.max(0, Math.min(1, ((px + shift) * dx * cos ** 2 + py * dy) / length)) : 0
    return distanceKm(point, { latitude: a.latitude + t * dy, longitude: a.longitude + t * dx }) <= radius
  })
}

/** Keep only nearby placements; a multi-location article appears once in the list. */
export function nearbyNews(data: ReturnType<typeof mapNews>, entities: Point[], routes: Point[][], radius = NEWS_PROXIMITY_KM) {
  const places = data.places.filter(place => entities.some(entity => distanceKm(place, entity) <= radius)
    || routes.some(route => route.some((point, index) => index === 0
      ? distanceKm(place, point) <= radius : nearSegment(place, route[index - 1], point, radius))))
  const urls = new Set(places.flatMap(place => place.articles.map(article => article.url)))
  return { places, urls, mapped: urls.size }
}
