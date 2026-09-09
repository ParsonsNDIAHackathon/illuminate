export interface GlobeMarker {
  id: string
  name: string
  longitude: number
  latitude: number
  color: string
  text?: string
  selected?: boolean
  news?: boolean
}
export interface GlobeRoute {
  id: string
  name: string
  points: { longitude: number; latitude: number }[]
  color: string
  dashed?: boolean
  selected?: boolean
}
