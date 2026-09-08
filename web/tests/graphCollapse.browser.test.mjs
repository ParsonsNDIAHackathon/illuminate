// The canvas collapses same-name entities when it is zoomed out. That grouping used to lock every
// member, which also froze the one node still painted: the user could no longer drag the merged
// organisation. These tests drive the real canvas over CDP and check the group still moves.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import test, { after, before } from 'node:test'

const port = 4181
const cdpPort = 9241
let vite
let chromium
let socket
let sequence = 0
const pending = new Map()

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
async function waitFor(check, message, timeout = 15000) {
  const started = Date.now()
  while (Date.now() - started < timeout) {
    const result = await check()
    if (result) return result
    await sleep(75)
  }
  throw new Error(`Timed out waiting for ${message}`)
}

function command(method, params = {}) {
  const id = ++sequence
  socket.send(JSON.stringify({ id, method, params }))
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }))
}

async function evaluate(expression) {
  const response = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (response.result.exceptionDetails) throw new Error(response.result.exceptionDetails.text)
  return response.result.result.value
}

async function open(path) {
  await command('Page.navigate', { url: `http://127.0.0.1:${port}${path}` })
  await waitFor(() => evaluate('document.readyState === "complete"'), 'page load')
}

/** Zoom past the collapse threshold and let the canvas regroup. The initial fit animates, so the
 *  zoom is re-applied until it sticks. */
async function setZoom(zoom) {
  await waitFor(async () => {
    await evaluate(`(() => { window.__cy.stop(); window.__cy.zoom({ level: ${zoom}, renderedPosition: { x: 0, y: 0 } }); return true })()`)
    await sleep(150)
    return evaluate(`Math.abs(window.__cy.zoom() - ${zoom}) < 0.01`)
  }, `zoom ${zoom}`)
  await sleep(100)
}

before(async () => {
  vite = spawn('npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(port)], { stdio: 'ignore' })
  await waitFor(async () => {
    try { return (await fetch(`http://127.0.0.1:${port}`)).ok } catch { return false }
  }, 'Vite server')

  chromium = spawn('chromium', [
    '--headless=new', '--no-sandbox', '--disable-gpu',
    `--remote-debugging-port=${cdpPort}`, '--user-data-dir=/tmp/illuminate-graph-collapse-browser-test',
    'about:blank',
  ], { stdio: 'ignore' })
  const target = await waitFor(async () => {
    try {
      const pages = await (await fetch(`http://127.0.0.1:${cdpPort}/json`)).json()
      return pages.find(page => page.type === 'page')
    } catch { return false }
  }, 'Chromium debugger')

  socket = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true })
    socket.addEventListener('error', reject, { once: true })
  })
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data)
    if (!message.id || !pending.has(message.id)) return
    const waiter = pending.get(message.id)
    pending.delete(message.id)
    if (message.error) waiter.reject(new Error(message.error.message))
    else waiter.resolve(message)
  })
  await command('Page.enable')
  await command('Runtime.enable')
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `
    (() => {
      const graph = {
        nodes: [
          { id: 'ray-1', label: 'Entity', layer: 'entities', name: 'Raytheon Company', props: {} },
          { id: 'ray-2', label: 'Entity', layer: 'entities', name: 'RAYTHEON COMPANY', props: {} },
          { id: 'other', label: 'Entity', layer: 'entities', name: 'Atlas Precision', props: {} },
        ],
        edges: [
          { id: 'e1', source: 'ray-1', target: 'other', type: 'SUPPLIES', props: {} },
        ],
      };
      const json = body => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }));
      window.fetch = input => {
        const url = String(input);
        if (url.includes('/api/workspace')) return json({ root_id: null, root_label: null, permission_mode: 'ask_always', model_strong: null, model_fast: null, openai_base_url: null, layers: {} });
        if (url.includes('/api/permissions')) return json({ pending: [], history: [] });
        if (url.includes('/api/jobs')) return json([]);
        if (url.includes('/api/claims')) return json([]);
        if (url.includes('/api/graph/programs')) return json({ items: [] });
        if (url.includes('/api/graph')) return json({ subgraph: graph, nodes: graph.nodes, edges: graph.edges });
        return json({});
      };
    })();
  ` })

  // The first visit warms Vite's dependency optimiser (cytoscape and its layout plugins); that
  // pass reloads the page and can drop the view's dynamic import, so the visit is retried.
  await open('/explorer')
  await waitFor(async () => {
    if (await evaluate('!!window.__cy')) return true
    await open('/explorer')
    return evaluate('!!window.__cy')
  }, 'the explorer canvas to mount')
  await waitFor(() => evaluate('!!window.__cy && window.__cy.nodes().length >= 3'), 'graph on the canvas')
  // The live force simulation would keep nudging positions under the assertions below.
  await evaluate('(() => { window.__cy.layout({ name: "preset" }).run(); return true })()')
})

after(() => {
  socket?.close()
  chromium?.kill()
  vite?.kill()
})

test('the painted node of a collapsed same-name group stays draggable', async () => {
  await setZoom(0.5)
  assert.equal(await evaluate('window.__cy.getElementById("ray-1").locked()'), false, 'anchor must stay unlocked')
  assert.equal(await evaluate('window.__cy.getElementById("ray-2").locked()'), true, 'duplicate stays pinned')
  assert.equal(await evaluate('window.__cy.getElementById("ray-2").hasClass("same-name-duplicate")'), true)

  const moved = await evaluate(`(() => {
    const cy = window.__cy;
    const anchor = cy.getElementById('ray-1');
    const before = { ...anchor.position() };
    anchor.position({ x: before.x + 140, y: before.y - 90 });
    const after = anchor.position();
    const follower = cy.getElementById('ray-2').position();
    return { dx: after.x - before.x, dy: after.y - before.y, gap: Math.hypot(after.x - follower.x, after.y - follower.y) };
  })()`)
  assert.equal(moved.dx, 140, 'the merged node itself moves')
  assert.equal(moved.dy, -90)
  assert.ok(moved.gap < 1, `grouped duplicate follows the painted node (gap ${moved.gap})`)
})

test('zooming back in releases every member of the group', async () => {
  await setZoom(1.5)
  assert.equal(await evaluate('window.__cy.getElementById("ray-1").locked()'), false)
  assert.equal(await evaluate('window.__cy.getElementById("ray-2").locked()'), false)
  assert.equal(await evaluate('window.__cy.getElementById("ray-2").hasClass("same-name-duplicate")'), false)
})
