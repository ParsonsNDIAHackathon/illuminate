/**
 * How a chat message is drawn, and where its links go.
 *
 * The chat's job is to hand back things — a report it just wrote, an entity it resolved —
 * and until now the answer could only *name* them: "it is on the Reports tab" is a
 * navigation instruction the reader has to carry out by hand. So a destination the answer
 * mentions becomes a link, and a destination a tool produced becomes a button.
 *
 * Two rules hold this together:
 *
 * 1. **A link is resolved, never trusted.** The model writes an href; this module decides
 *    what it means, against the routes web/src/router.ts actually declares (the server
 *    keeps the same list in api/illuminate/links.py). An href that resolves to nothing is
 *    rendered as its own label in plain text — a dead button is worse than a sentence.
 * 2. **Internal links navigate, they do not reload.** A route push keeps the canvas, the
 *    conversation and the styling that the answer just applied; an <a href> would throw all
 *    three away to arrive at the same page.
 *
 * Explicit extension: this module is covered by tests/chatMarkup.test.ts, which runs under
 * node's type stripping and resolves imports the way node does, not the way vite does.
 */

/** In-app routes a link may point at. Mirrors ROUTE_PATTERNS in api/illuminate/links.py. */
const ROUTES: RegExp[] = [
  /^\/reports\/[\w.:-]+$/,
  /^\/entities\/[\w.:-]+$/,
  /^\/people\/[\w.:-]+$/,
  /^\/(reports|entities|people|risk|artifacts|claims|connectors|settings)$/,
]

/** "Show it on the canvas" is an action, not a route. */
const CANVAS_SCHEME = 'canvas:'

export type ChatLink =
  | { type: 'route'; to: string }
  | { type: 'canvas'; id: string }
  | { type: 'external'; url: string }

/** What an href means, or null if it means nothing this app can do. */
export function resolveChatLink(href: string | null | undefined): ChatLink | null {
  const h = (href || '').trim()
  if (!h) return null
  if (h.startsWith(CANVAS_SCHEME)) {
    const id = h.slice(CANVAS_SCHEME.length).trim()
    return /^[\w.:-]+$/.test(id) ? { type: 'canvas', id } : null
  }
  if (ROUTES.some(r => r.test(h))) return { type: 'route', to: h }
  // Only the two schemes that can be safely put behind a click. javascript:, data: and a
  // protocol-relative //host are all refused here rather than filtered downstream.
  if (/^https?:\/\/[^\s"'<>]+$/i.test(h)) return { type: 'external', url: h }
  return null
}

export function esc(s: string): string {
  return s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' } as Record<string, string>)[c])
}

/** The anchor for a resolved link. Internal ones carry the destination in a data attribute:
 *  ChatRail intercepts the click and pushes the route, so href is only there for middle-click
 *  and "copy link address". */
export function anchor(link: ChatLink, label: string): string {
  const text = esc(label)
  if (link.type === 'route') return `<a class="chat-link" href="${esc(link.to)}" data-route="${esc(link.to)}">${text}</a>`
  if (link.type === 'canvas') return `<a class="chat-link" href="#" data-canvas="${esc(link.id)}">${text}</a>`
  return `<a class="chat-link" href="${esc(link.url)}" target="_blank" rel="noopener noreferrer">${text}</a>`
}

// One pass, two shapes: [label](href), and a bare URL minus the trailing punctuation that
// belongs to the sentence rather than to the link. Matching both in a single alternation is
// what keeps an emitted anchor from being re-scanned by the next pass and nested in itself.
const LINKISH = /\[([^\]\n]+)\]\(([^)\s]+)\)|(https?:\/\/[^\s<>()]*[^\s<>().,;:!?'"])/g

/**
 * Message text to HTML: markdown links, bare URLs, `code`, **bold**, newlines.
 *
 * Escaping happens first and once, so everything after it composes over text that can no
 * longer close a tag. The link pass then re-inserts markup deliberately, on hrefs that
 * resolveChatLink has already vouched for.
 */
export function renderChatText(text: string | null | undefined): string {
  const escaped = esc(text || '')
  let out = ''
  let at = 0
  for (const m of escaped.matchAll(LINKISH)) {
    const [whole, label, href, bare] = m
    out += inline(escaped.slice(at, m.index))
    at = m.index + whole.length
    const link = resolveChatLink(unesc(href ?? bare))
    // A link nobody can follow degrades to its label — the sentence still reads.
    out += link ? anchor(link, unesc(label ?? bare)) : inline(esc(unesc(label ?? bare)))
  }
  return out + inline(escaped.slice(at))
}

/** The markup that is not a link: `code`, **bold**, newlines. */
function inline(s: string): string {
  return s
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/\n/g, '<br>')
}

/** Undo the first escape pass for text that is about to be re-escaped or validated. */
function unesc(s: string): string {
  return s.replace(/&quot;/g, '"').replace(/&gt;/g, '>').replace(/&lt;/g, '<').replace(/&amp;/g, '&')
}

/** A structured link from a tool result (api/illuminate/links.py). */
export interface MessageLink { kind: string; label: string; href: string; id?: string; description?: string }

/** The icon a link button wears, by what it opens. */
export function linkIcon(kind: string): string {
  return ({ report: 'mdi-file-document-outline', entity: 'mdi-domain', person: 'mdi-account-outline',
            canvas: 'mdi-graph-outline' } as Record<string, string>)[kind] || 'mdi-open-in-new'
}

/** Buttons are only worth drawing for destinations that exist. */
export function usableLinks(links: MessageLink[] | undefined): MessageLink[] {
  return (links || []).filter(l => l && l.href && resolveChatLink(l.href))
}
