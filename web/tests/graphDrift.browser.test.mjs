// The live cola simulation must settle. Cola takes the ideal separation of a pair of nodes from the
// shortest path between them, and gives a pair with no path at all Number.MAX_VALUE — so a single
// stranded node used to push the whole graph towards a separation of 1e308 and nodes streamed off
// the canvas forever. Layer toggles strand nodes routinely, so the fixture below carries one. These
// tests drive the real canvas with the simulation running and assert the positions come to rest.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import test, { after, before } from 'node:test'

const port = 4183
const cdpPort = 9243
let vite
let chromium
let socket
let sequence = 0
const pending = new Map()

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
async function waitFor(check, message, timeout = 20000) {
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

/** Total distance every node travels over `ms` of wall clock, with the simulation left running. */
async function drift(ms) {
  await evaluate(`(() => { window.__probe = {}; window.__cy.nodes().forEach(n => { window.__probe[n.id()] = { ...n.position() } }); return true })()`)
  await sleep(ms)
  return evaluate(`(() => {
    let total = 0, worst = 0, worstId = null;
    window.__cy.nodes().forEach(n => {
      const was = window.__probe[n.id()]; if (!was) return;
      const now = n.position();
      const d = Math.hypot(now.x - was.x, now.y - was.y);
      total += d;
      if (d > worst) { worst = d; worstId = n.id() }
    });
    return { total, worst, worstId };
  })()`)
}

before(async () => {
  vite = spawn('npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(port)], { stdio: 'ignore' })
  await waitFor(async () => {
    try { return (await fetch(`http://127.0.0.1:${port}`)).ok } catch { return false }
  }, 'Vite server')

  chromium = spawn('chromium', [
    '--headless=new', '--no-sandbox', '--disable-gpu',
    `--remote-debugging-port=${cdpPort}`, '--user-data-dir=/tmp/illuminate-graph-drift-browser-test',
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
  // A hub with suppliers, plus stranded entities with no edge at all — the shape a layer
  // toggle leaves behind, and the case that used to make cola diverge.
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `
    (() => {
      const dup = (slug, name, i) => ({ id: slug + '-' + i, label: 'Entity', layer: 'entities', name, props: {} });
      const nodes = [];
      const edges = [];
      [['ray', 'Raytheon Company'], ['lm', 'Lockheed Martin'], ['bae', 'BAE Systems']].forEach(([slug, name]) => {
        nodes.push(dup(slug, name, 1), dup(slug, name.toUpperCase(), 2));
        edges.push({ id: 'e-' + slug, source: slug + '-1', target: 'hub', type: 'SUPPLIES', props: {} });
      });
      nodes.push({ id: 'hub', label: 'Entity', layer: 'entities', name: 'Atlas Precision', props: {} });
      for (let i = 0; i < 4; i++) nodes.push({ id: 'stranded-' + i, label: 'Entity', layer: 'entities', name: 'Stranded Holdings ' + i, props: {} });
      const graph = { nodes, edges };
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

  await open('/')
  await waitFor(async () => {
    if (await evaluate('!!window.__cy')) return true
    await open('/')
    return evaluate('!!window.__cy')
  }, 'the explorer canvas to mount')
  await waitFor(() => evaluate('!!window.__cy && window.__cy.nodes().length >= 11'), 'graph on the canvas')
})

test('the live simulation settles when the canvas carries stranded nodes', async () => {
  await sleep(4000)
  const moved = await drift(2000)
  assert.ok(
    moved.worst < 60,
    `nodes must come to rest (worst ${moved.worstId} moved ${moved.worst.toFixed(1)}px, total ${moved.total.toFixed(1)}px)`,
  )
})

test('the graph does not fly apart', async () => {
  const spread = await evaluate(`(() => {
    const bb = window.__cy.nodes().boundingBox();
    return { w: bb.w, h: bb.h };
  })()`)
  assert.ok(spread.w < 8000 && spread.h < 8000, `graph must stay bounded (bbox ${spread.w.toFixed(0)}x${spread.h.toFixed(0)})`)
})

after(() => {
  socket?.close()
  chromium?.kill()
  vite?.kill()
})
