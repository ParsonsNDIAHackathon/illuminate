import { Cartesian3, Cartesian4, Ellipsoid, EllipsoidalOccluder, Matrix4 } from 'cesium'
import type { GlobeMarker } from './cesiumMap.ts'

/** Test the marker against the globe horizon and the camera's actual screen bounds. */
export function visibleMarkerIds(markers: GlobeMarker[], camera: {
  positionWC: Cartesian3; viewMatrix: Matrix4; frustum: { projectionMatrix: Matrix4 }
}, width: number, height: number): string[] {
  if (width <= 0 || height <= 0) return []
  const horizon = new EllipsoidalOccluder(Ellipsoid.WGS84, camera.positionWC)
  const transform = Matrix4.multiply(camera.frustum.projectionMatrix, camera.viewMatrix, new Matrix4())
  return markers.filter(marker => {
    const position = Cartesian3.fromDegrees(marker.longitude, marker.latitude, 1500)
    if (!horizon.isPointVisible(position)) return false
    const clip = Matrix4.multiplyByVector(transform, new Cartesian4(position.x, position.y, position.z, 1), new Cartesian4())
    if (clip.w <= 0 || clip.z < -clip.w || clip.z > clip.w) return false
    const x = (clip.x / clip.w + 1) * width / 2
    const y = (1 - clip.y / clip.w) * height / 2 - (marker.news ? 26 : 0)
    const radius = marker.inspected ? (marker.news ? 22 : 24) : marker.news ? 14 * (marker.selected ? 1.2 : 1) : marker.text ? 12.5 : 5
    return x + radius >= 0 && x - radius <= width && y + radius >= 0 && y - radius <= height
  }).map(marker => marker.id)
}
