import assert from 'node:assert/strict'
import test from 'node:test'
import { Cartesian3, Matrix4 } from 'cesium'
import { visibleMarkerIds } from '../src/mapVisibility.ts'

function camera(longitude = 0, height = 18000000) {
  const positionWC = Cartesian3.fromDegrees(longitude, 0, height)
  const direction = Cartesian3.normalize(Cartesian3.negate(positionWC, new Cartesian3()), new Cartesian3())
  const up = Cartesian3.UNIT_Z
  const right = Cartesian3.cross(direction, up, new Cartesian3())
  return { positionWC, viewMatrix: Matrix4.computeView(positionWC, direction, up, right, new Matrix4()),
    frustum: { projectionMatrix: Matrix4.computePerspectiveFieldOfView(Math.PI / 3, 1, 100, 1e8, new Matrix4()) } }
}
const marker = (id: string, longitude: number, latitude = 0) => ({ id, longitude, latitude, name: id, color: '#ffffff' })
test('far-side markers are excluded even when they project inside the viewport', () => {
  assert.deepEqual(visibleMarkerIds([marker('front', 0), marker('back', 180)], camera(), 600, 600), ['front'])
})
test('zooming excludes offscreen markers on the facing hemisphere', () => {
  const markers = [marker('center', 0), marker('east', 10)]
  assert.deepEqual(visibleMarkerIds(markers, camera(), 600, 600), ['center', 'east'])
  assert.deepEqual(visibleMarkerIds(markers, camera(0, 100000), 600, 600), ['center'])
})
test('the date line is continuous when the camera faces the Pacific', () => {
  assert.deepEqual(visibleMarkerIds([marker('east', 179), marker('west', -179), marker('back', 0)], camera(180), 600, 600), ['east', 'west'])
})
test('hidden or zero-size map has no visible markers', () => {
  assert.deepEqual(visibleMarkerIds([marker('center', 0)], camera(), 0, 600), [])
})
