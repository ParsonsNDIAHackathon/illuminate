import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const explorer = readFileSync(new URL('../src/views/Explorer.vue', import.meta.url), 'utf8')
const report = readFileSync(new URL('../src/views/EntityReport.vue', import.meta.url), 'utf8')
const portfolio = readFileSync(new URL('../src/views/Portfolio.vue', import.meta.url), 'utf8')

test('finding traces carry and apply their mission before loading the vendor', () => {
  assert.match(report, /root_id: reportRoot\.value \|\| undefined,\s*vendor: props\.id/)
  const vendorBranch = explorer.slice(explorer.indexOf('if (vendor) {'), explorer.indexOf('} else {', explorer.indexOf('if (vendor) {')))
  const missionFocus = vendorBranch.indexOf('await graph.focus(missionRoot')
  const vendorLoad = vendorBranch.indexOf('await graph.loadNeighbourhood(vendor')
  assert.ok(missionFocus >= 0, 'vendor trace must apply the incoming mission root')
  assert.ok(vendorLoad > missionFocus, 'mission root must be applied before the vendor trace is loaded')
})

test('query-only mission changes reload report and portfolio scopes', () => {
  assert.match(report, /watch\(\[\(\) => props\.id, reportRoot\], load, \{ immediate: true \}\)/)
  assert.match(portfolio, /watch\(missionRoot, load, \{ immediate: true \}\)/)
  assert.match(report, /reportRequest\.isCurrent\(generation\)/)
  assert.match(portfolio, /portfolioRequests\.currentScope\(\) === generation/)
})