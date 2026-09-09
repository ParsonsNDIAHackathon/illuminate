/** Match marker centres to the map's projected viewBox, including boundary points. */
export function inMapViewport(place: { latitude: number | null; longitude: number | null }, center: readonly number[], zoom: number) {
  if (place.latitude === null || place.longitude === null || !Number.isFinite(place.latitude) || !Number.isFinite(place.longitude)) return false
  const x = (place.longitude + 180) * 3, y = (90 - place.latitude) * 3
  return x >= center[0]! - 540 / zoom && x <= center[0]! + 540 / zoom
    && y >= center[1]! - 270 / zoom && y <= center[1]! + 270 / zoom
}

/** A multi-country article appears once if any of its displayed markers is visible. */
export function visibleNewsArticles<T extends { url: string }>(articles: T[], places: { code: string; articles: T[] }[], location = '') {
  const urls = new Set(places.filter(p => !location || p.code === location).flatMap(p => p.articles.map(a => a.url)))
  return articles.filter(a => urls.has(a.url))
}
