import { defineStore } from 'pinia'
import { chatSocket } from '../api/ws'
import { useGraph } from './graph'
import { usePermissions } from './permissions'
import { useJobs } from './jobs'

export interface ToolEvent { name: string; args?: any; ok?: boolean; cypher?: string | null; params?: any; summary?: string; permission?: any; notes?: string[] }
export interface ChatMessage { id: string; role: 'user' | 'assistant' | 'system'; text: string; streaming?: boolean; tools?: ToolEvent[]; cypher?: any[]; legend?: any[]; error?: string; permissions?: any[] }

let seq = 0
const mid = () => `m${Date.now()}_${seq++}`

export const useChat = defineStore('chat', {
  state: () => ({ messages: [] as ChatMessage[], conversationId: null as string | null, busy: false, connected: false, modelKey: false, bound: false }),
  actions: {
    bind() {
      if (this.bound) return
      this.bound = true
      chatSocket.on((ev) => this.handle(ev))
      chatSocket.connect()
    },
    send(text: string, canvasIds?: string[], layers?: Record<string, boolean>) {
      this.messages.push({ id: mid(), role: 'user', text })
      this.messages.push({ id: mid(), role: 'assistant', text: '', streaming: true, tools: [] })
      this.busy = true
      chatSocket.send({ type: 'message', text, conversation_id: this.conversationId, canvas_ids: canvasIds?.slice(0, 200), layers })
    },
    current(): ChatMessage | undefined { return [...this.messages].reverse().find(m => m.role === 'assistant' && m.streaming) },
    handle(ev: any) {
      const graph = useGraph()
      switch (ev.type) {
        case 'socket': this.connected = !!ev.connected; break
        case 'hello': this.modelKey = !!ev.model_key; break
        case 'turn_start': this.conversationId = ev.conversation_id; break
        case 'delta': { const m = this.current(); if (m) m.text += ev.text; break }
        case 'tool_call': { const m = this.current(); m?.tools!.push({ name: ev.name, args: ev.args }); break }
        case 'tool_result': {
          const m = this.current()
          if (m) { const t = [...m.tools!].reverse().find(t => t.name === ev.name && t.ok === undefined); if (t) Object.assign(t, { ok: ev.ok, cypher: ev.cypher, params: ev.params, summary: ev.summary, permission: ev.permission, notes: ev.notes }) }
          if (ev.subgraph) graph.merge(ev.subgraph)
          if (ev.style_ops?.length) graph.applyStyleOps(ev.style_ops)
          if (ev.cypher) graph.lastCypher = { statement: ev.cypher, params: ev.params }
          break
        }
        case 'answer': {
          const m = this.current()
          if (m) { m.text = ev.answer || m.text; m.streaming = false; m.cypher = ev.cypher; m.legend = ev.legend; m.permissions = ev.permissions }
          if (ev.subgraph) graph.merge(ev.subgraph)
          if (ev.style_ops?.length) graph.applyStyleOps(ev.style_ops)
          this.busy = false
          break
        }
        case 'error': { const m = this.current(); if (m) { m.error = ev.message; m.streaming = false } this.busy = false; break }
        case 'model_unavailable': { const m = this.current(); if (m) m.error = ev.message; break }
        case 'permission_request': usePermissions().push(ev.payload); break
        case 'permission_resolved': case 'permission_failed': usePermissions().resolve(ev.payload); break
        case 'job_update': useJobs().update(ev.payload); break
      }
    },
    reset() { this.messages = []; this.conversationId = null },
  },
})
