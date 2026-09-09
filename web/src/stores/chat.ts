import { defineStore } from 'pinia'
import { chatSocket } from '../api/ws'
import { useGraph } from './graph'
import { usePermissions } from './permissions'
import { useJobs } from './jobs'
import type { MessageLink } from '../chat/markup'

export interface ToolEvent { name: string; args?: any; ok?: boolean; cypher?: string | null; params?: any; summary?: string; permission?: any; notes?: string[] }
// links: where this answer can take you — a report to open, a page to visit. Built by the
// server (api/illuminate/links.py) so the button is there whether or not the model mentioned it.
export interface ChatMessage { id: string; role: 'user' | 'assistant' | 'system'; text: string; streaming?: boolean; tools?: ToolEvent[]; cypher?: any[]; legend?: any[]; links?: MessageLink[]; error?: string; permissions?: any[] }

let seq = 0
const mid = () => `m${Date.now()}_${seq++}`

/** One button per destination: the same report asked for twice in a turn is one door. */
function dedupeLinks(links: MessageLink[]): MessageLink[] {
  const seen = new Set<string>()
  return links.filter(l => l?.href && !seen.has(l.href) && seen.add(l.href))
}

export const useChat = defineStore('chat', {
  state: () => ({ messages: [] as ChatMessage[], conversationId: null as string | null, busy: false, connected: false, modelKey: false, bound: false }),
  actions: {
    bind() {
      if (this.bound) return
      this.bound = true
      chatSocket.on((ev) => this.handle(ev))
      chatSocket.connect()
    },
    send(text: string, canvasIds?: string[], layers?: Record<string, boolean>, focusId?: string | null, focusLabel?: string | null) {
      this.messages.push({ id: mid(), role: 'user', text })
      this.messages.push({ id: mid(), role: 'assistant', text: '', streaming: true, tools: [] })
      this.busy = true
      // The whole canvas, not a sample of it: the prompt only ever quotes the first 80 (see
      // llm/prompts.turn_context), but a tool that colours what is on screen — apply_color_scheme
      // — has to be given all of it or it leaves the rest of the graph unpainted.
      chatSocket.send({ type: 'message', text, conversation_id: this.conversationId, canvas_ids: canvasIds?.slice(0, 2000), layers, focus_id: focusId ?? null, focus_label: focusLabel ?? null })
    },
    current(): ChatMessage | undefined { return [...this.messages].reverse().find(m => m.role === 'assistant' && m.streaming) },
    handle(ev: any) {
      const graph = useGraph()
      switch (ev.type) {
        case 'socket': this.connected = !!ev.connected; break
        case 'hello': this.modelKey = !!ev.model_key; break
        // A turn's styling is added to what is already on the canvas, so mark where it
        // starts — the answer resends the whole turn and has to overwrite, not double up.
        case 'turn_start': this.conversationId = ev.conversation_id; graph.beginStyleTurn(); break
        case 'delta': { const m = this.current(); if (m) m.text += ev.text; break }
        case 'tool_call': { const m = this.current(); m?.tools!.push({ name: ev.name, args: ev.args }); break }
        case 'tool_result': {
          const m = this.current()
          if (m) { const t = [...m.tools!].reverse().find(t => t.name === ev.name && t.ok === undefined); if (t) Object.assign(t, { ok: ev.ok, cypher: ev.cypher, params: ev.params, summary: ev.summary, permission: ev.permission, notes: ev.notes }) }
          // A report is openable the moment it is written, so its button lands with the
          // tool result rather than waiting for the model to finish its sentence.
          if (m && ev.links?.length) m.links = dedupeLinks([...(m.links || []), ...ev.links])
          if (ev.subgraph) graph.merge(ev.subgraph)
          if (ev.style_ops?.length) graph.appendStyleOps(ev.style_ops)
          if (ev.cypher) graph.lastCypher = { statement: ev.cypher, params: ev.params }
          break
        }
        case 'answer': {
          const m = this.current()
          if (m) { m.text = ev.answer || m.text; m.streaming = false; m.cypher = ev.cypher; m.legend = ev.legend; m.permissions = ev.permissions; m.links = dedupeLinks(ev.links || m.links || []) }
          if (ev.subgraph) graph.merge(ev.subgraph)
          if (ev.style_ops?.length) graph.setTurnStyleOps(ev.style_ops)
          this.busy = false
          break
        }
        case 'error': { const m = this.current(); if (m) { m.error = ev.message; m.streaming = false } this.busy = false; break }
        case 'permission_request': usePermissions().push(ev.payload); break
        case 'permission_resolved': case 'permission_failed': usePermissions().resolve(ev.payload); break
        case 'job_update': useJobs().update(ev.payload); break
        // Any committed write, from any source — this chat, another tab, MCP, or the
        // enrichment worker — arrives here so the canvas never needs a reload.
        case 'graph_delta': graph.applyDelta(ev.payload?.subgraph, ev.payload?.focus); break
      }
    },
    reset() { this.messages = []; this.conversationId = null },
  },
})
