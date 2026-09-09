export type NewsArticle = { url: string; title: string; seendate: string; domain: string; language: string }
type Country = { code: string; name: string; latitude: number; longitude: number }
const aliases: Record<string, string[]> = {
  US: ['United States', 'USA', 'U.S.'], GB: ['United Kingdom', 'Britain', 'UK'],
  UA: ['Ukraine', 'Ukrainian'], RU: ['Russia', 'Russian'], CN: ['China', 'Chinese'],
  IL: ['Israel', 'Israeli'], PS: ['Palestine', 'Palestinian', 'Gaza'],
  IR: ['Iran', 'Iranian'], TW: ['Taiwan', 'Taiwanese'], KR: ['South Korea'], KP: ['North Korea'],
}
// Headlines supply approximate country mentions, never inferred incident coordinates.
// Do not use sourcecountry: it describes the publisher, not the reported location.
export function mapNews(articles: NewsArticle[], countries: Country[]) {
  const patterns = countries.map(country => ({ country, patterns: [country.name, ...(aliases[country.code] || [])]
    .filter(name => name.length > 2).map(name => new RegExp(`(?<![\\p{L}])${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![\\p{L}])`, 'iu')) }))
  const placed = new Set<string>()
  const places = patterns.map(({ country, patterns }) => ({ ...country, articles: articles.filter(article => {
    const match = patterns.some(pattern => pattern.test(article.title))
    if (match) placed.add(article.url)
    return match
  }) })).filter(place => place.articles.length)
  return { places, mapped: placed.size, unmapped: articles.filter(article => !placed.has(article.url)) }
}
export function newsDate(value: string) {
  return /^\d{8}T\d{6}Z$/.test(value) ? `${value.slice(0,4)}-${value.slice(4,6)}-${value.slice(6,8)} ${value.slice(9,11)}:${value.slice(11,13)} UTC` : value
}
