import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import test, { after, before } from 'node:test'

const port = 4178
const cdpPort = 9238
let vite
let chromium
let socket
let sequence = 0
const pending = new Map()

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
async function waitFor(check, message, timeout = 10000) {
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
async function open(mode = 'loaded') {
  await command('Page.navigate', { url: `http://127.0.0.1:${port}/interoperability?mode=${mode}` })
  await waitFor(
    () => evaluate(`location.pathname === '/interoperability' && new URL(location.href).searchParams.get('mode') === ${JSON.stringify(mode)} && document.readyState === 'complete'`),
    'page load',
  )
}
async function bodyIncludes(text) {
  return evaluate(`document.body.innerText.includes(${JSON.stringify(text)})`)
}

before(async () => {
  vite = spawn('npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(port)], { stdio: 'ignore', detached: true })
  await waitFor(async () => {
    try { return (await fetch(`http://127.0.0.1:${port}`)).ok } catch { return false }
  }, 'Vite server')
  chromium = spawn('chromium', [
    '--headless=new', '--no-sandbox', '--disable-gpu',
    `--remote-debugging-port=${cdpPort}`, '--user-data-dir=/tmp/illuminate-interoperability-browser-test',
    'about:blank',
  ], { stdio: 'ignore', detached: true })
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
      const json = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
      const queryMode = () => new URL(location.href).searchParams.get('mode') || 'loaded';
      window.fetch = (input, options = {}) => {
        const url = String(input);
        if (url.includes('/api/workspace')) return json({ root_id: null, root_label: null, permission_mode: 'ask_always', model_strong: null, model_fast: null, openai_base_url: null, layers: {} });
        if (url.includes('/api/permissions')) return json({ pending: [], history: [] });
        if (url.includes('/api/jobs') || url.includes('/api/claims')) return json([]);
        if (url.includes('/api/exports/v1/findings?limit=10')) {
          if (queryMode() === 'error') return json({ detail: 'export unavailable' }, 503);
          return json({
            meta: { schema_version: '1.1', generated_at: '2026-09-08T12:00:00Z', count: queryMode() === 'empty' ? 0 : 1, limit: 10, next_cursor: 'cursor', watermark: 'watermark-7' },
            findings: queryMode() === 'empty' ? [] : [{ finding_id: 'fnd_1', subject_id: 'ent_1', subject_name: 'Supplier One', predicate: 'sole_source_dependency', classification: 'UNCLASSIFIED', truth_status: 'committed', simulated: false, provenance: [{ source: 'test' }], paths: [] }],
          });
        }
        if (url.includes('/api/catalog/ndia/preview')) return json({ export_id: 'illuminate-insight-findings', export_version: '1.1', export_watermark: 'watermark-7', event: { id: 3, slug: 'ndia-global-defense-hackathon-main-event-washington-dc', title: 'NDIA Global Defense Hackathon / Main Event: Washington, DC' }, metadata: {}, confirmation_token: 'confirmation-token-long-enough', schema_valid: true, publication_ready: false, credential_configured: false, operator_authorization_configured: false, contribution_state: 'published', remote_dataset_id: null, message: 'No remote identity' });
        if (url.includes('/api/catalog/ndia/status')) return json({ export_id: 'illuminate-insight-findings', export_version: '1.1', dataset_id: null, contribution_state: 'unknown', message: 'No remote dataset is recorded', dry_run: false, idempotent: false, submitted_at: null, metadata: {} });
        if (url.includes('/api/catalog/ndia/submit') && options.method === 'POST') return json({ export_id: 'illuminate-insight-findings', export_version: '1.1', dataset_id: null, contribution_state: 'validated_dry_run', message: 'Nothing was sent.', dry_run: true, idempotent: false, submitted_at: null, metadata: {} });
        return json({});
      };
    })();
  ` })
})

after(() => {
  socket?.close()
  if (chromium?.pid) try { process.kill(-chromium.pid, 'SIGTERM') } catch {}
  if (vite?.pid) try { process.kill(-vite.pid, 'SIGTERM') } catch {}
})

test('loaded export shows metadata, bounded downloads, links, and truthful catalog state', async () => {
  await open()
  await waitFor(() => bodyIncludes('Supplier One'), 'finding preview')
  const text = await evaluate('document.body.innerText')
  assert.match(text, /Schema 1.1/)
  assert.match(text, /PREVIEW COUNT[\s\S]*1/)
  assert.match(text, /DOWNLOAD JSON PAGE[\s\S]*DOWNLOAD NDJSON PAGE[\s\S]*DOWNLOAD CSV PAGE/)
  assert.match(text, /one bounded page of at most 1,000 findings/)
  assert.match(text, /UNKNOWN/)
  assert.doesNotMatch(text, /\bPUBLISHED\b/)
  const hrefs = await evaluate(`[...document.querySelectorAll('a')].map(a => a.getAttribute('href'))`)
  assert.ok(hrefs.includes('/api/exports/v1/schema'))
  assert.ok(hrefs.includes('/api/exports/v1/fields'))
  assert.ok(hrefs.includes('/api/exports/v1/sample'))
})

test('empty and failed export states stay explicit', async () => {
  await open('empty')
  await waitFor(() => bodyIncludes('No findings are currently available.'), 'empty export')
  await open('error')
  await waitFor(() => bodyIncludes('Findings preview unavailable.'), 'export error')
})

test('dry run is visibly distinct from publication', async () => {
  await open()
  await waitFor(() => bodyIncludes('VALIDATE DRY RUN'), 'dry-run action')
  await evaluate(`[...document.querySelectorAll('button')].find(button => button.innerText.includes('VALIDATE DRY RUN')).click()`)
  await waitFor(() => bodyIncludes('VALIDATED DRY RUN'), 'dry-run result')
  assert.equal(await bodyIncludes('Nothing was sent.'), true)
})