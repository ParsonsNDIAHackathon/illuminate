import assert from 'node:assert/strict'
import test from 'node:test'

import { anchor, renderChatText, resolveChatLink, usableLinks } from '../src/chat/markup.ts'

// The chat renders model output as HTML, so this file has two jobs: prove that a
// destination the answer names becomes something you can click, and prove that nothing
// else does. The second is the one that matters — the text being escaped here was written
// by a language model over data fetched from the open web.

// --- what an href means ------------------------------------------------------------
test('in-app routes resolve to a route push', () => {
  for (const p of ['/reports/rp_a1', '/entities/ent_x', '/people/per_y', '/risk', '/settings']) {
    assert.deepEqual(resolveChatLink(p), { type: 'route', to: p })
  }
})

test('a canvas link is an action, not a route', () => {
  assert.deepEqual(resolveChatLink('canvas:ent_x'), { type: 'canvas', id: 'ent_x' })
})

test('http(s) is the only external scheme that survives', () => {
  assert.deepEqual(resolveChatLink('https://sam.gov/x'), { type: 'external', url: 'https://sam.gov/x' })
  for (const bad of ['javascript:alert(1)', 'data:text/html,<script>', 'file:///etc/passwd', '//evil.example.com', 'vbscript:x']) {
    assert.equal(resolveChatLink(bad), null, bad)
  }
})

test('a path the router does not have is not a link', () => {
  for (const bad of ['/dashboard', '/entities/ent_x/edit', '/reports/rp_a/../../etc', '/reports/rp_a/extra', '']) {
    assert.equal(resolveChatLink(bad)?.type, undefined, bad)
  }
  // the bare tabs that do exist still resolve
  assert.equal(resolveChatLink('/artifacts')?.type, 'route')
})

// --- rendering ---------------------------------------------------------------------
test('a markdown link to a report becomes an in-app anchor', () => {
  const html = renderChatText('Wrote [Risk assessment: E-2D](/reports/rp_a1) — 4 findings.')
  assert.match(html, /<a class="chat-link" href="\/reports\/rp_a1" data-route="\/reports\/rp_a1">Risk assessment: E-2D<\/a>/)
  assert.match(html, /4 findings\.$/)
})

test('a canvas link carries the node id for the composable to open', () => {
  assert.match(renderChatText('[Acme](canvas:ent_x)'), /data-canvas="ent_x">Acme<\/a>/)
})

test('an external link opens in a new tab and disowns the opener', () => {
  const html = renderChatText('See [the award](https://usaspending.gov/award/1).')
  assert.match(html, /target="_blank" rel="noopener noreferrer"/)
})

test('a link nobody can follow degrades to its label', () => {
  const html = renderChatText('Open [the dashboard](/dashboard) now')
  assert.equal(html, 'Open the dashboard now')
})

test('bare urls are linked; a trailing full stop stays in the sentence', () => {
  const html = renderChatText('Source: https://sam.gov/entity/ABC123.')
  assert.match(html, /href="https:\/\/sam\.gov\/entity\/ABC123"/)
  assert.match(html, /<\/a>\.$/)
})

test('a url inside a link label does not nest a second anchor', () => {
  const html = renderChatText('[see https://x.test/a for detail](/reports/rp_a1)')
  assert.equal(html.match(/<a /g)?.length, 1)
})

test('code, bold and newlines still render around links', () => {
  const html = renderChatText('**Done** — see [it](/reports/rp_a1)\nran `MATCH (n)`')
  assert.match(html, /<b>Done<\/b>/)
  assert.match(html, /<br>/)
  assert.match(html, /<code>MATCH \(n\)<\/code>/)
})

// --- nothing else becomes markup ---------------------------------------------------
test('markup in the message text is escaped, not rendered', () => {
  const html = renderChatText('<img src=x onerror="alert(1)"> & <b>bold</b>')
  assert.doesNotMatch(html, /<img/)
  assert.doesNotMatch(html, /<b>bold/)
  assert.match(html, /&lt;img/)
})

test('a link label cannot break out of the anchor', () => {
  const html = renderChatText('["><script>alert(1)</script>](/reports/rp_a1)')
  assert.doesNotMatch(html, /<script/)
  assert.match(html, /&quot;&gt;&lt;script&gt;/)
})

test('an href cannot break out of the attribute', () => {
  // No anchor at all: the quote is escaped before the href is ever read, so it matches no
  // route and the whole construction stays inert text.
  const html = renderChatText('[x](/reports/rp" onmouseover="alert(1))')
  assert.doesNotMatch(html, /<a /)
  assert.doesNotMatch(html, /"/)
})

test('anchors escape the destination they were built from', () => {
  assert.equal(anchor({ type: 'canvas', id: 'a"b' }, 'x'), '<a class="chat-link" href="#" data-canvas="a&quot;b">x</a>')
})

// --- structured links --------------------------------------------------------------
test('only links with a destination this app has get a button', () => {
  const links = [
    { kind: 'report', label: 'Risk assessment', href: '/reports/rp_a1' },
    { kind: 'entity', label: 'Nowhere', href: '/nope/x' },
    { kind: 'external', label: 'Bad', href: 'javascript:alert(1)' },
  ]
  assert.deepEqual(usableLinks(links).map(l => l.href), ['/reports/rp_a1'])
  assert.deepEqual(usableLinks(undefined), [])
})
