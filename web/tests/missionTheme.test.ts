import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const mission = readFileSync(new URL('../src/views/MissionEntry.vue', import.meta.url), 'utf8')
const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
const workspace = readFileSync(new URL('../src/stores/workspace.ts', import.meta.url), 'utf8')

test('mission custom surfaces switch from the Vuetify dark theme boundary', () => {
  assert.match(mission, /:global\(\.v-theme--dark \.mission\)/)

  for (const token of ['--paper', '--ink', '--muted', '--line', '--panel', '--advisory', '--state', '--simulation', '--hover', '--focus']) {
    assert.match(mission, new RegExp(`${token}:`, 'g'), `${token} should have theme palette values`)
    assert.match(mission, new RegExp(`var\\(${token}\\)`), `${token} should style a mission surface`)
  }

  assert.match(mission, /\.preset:focus-visible,.workflow a:focus-visible\{outline:2px solid var\(--focus\)/)
  assert.match(mission, /\.workflow a:hover,.workflow a:focus-visible\{background:var\(--hover\)/)
})

test('the active and persisted theme remains wired to Vuetify', () => {
  assert.match(app, /<v-app :theme="ws\.theme">/)
  assert.match(app, /ws\.setTheme\(ws\.theme === 'dark' \? 'light' : 'dark'\)/)
  assert.match(workspace, /theme: \(localStorage\.getItem\('illuminate\.theme'\)/)
  assert.match(workspace, /localStorage\.setItem\('illuminate\.theme', t\)/)
})