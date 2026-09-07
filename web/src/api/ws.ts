type Handler = (ev: any) => void

class ChatSocket {
  private ws: WebSocket | null = null
  private handlers = new Set<Handler>()
  private queue: string[] = []
  private timer: any = null
  connected = false

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    this.ws = new WebSocket(`${proto}://${location.host}/ws/chat?user=local`)
    this.ws.onopen = () => { this.connected = true; this.queue.splice(0).forEach(m => this.ws!.send(m)); this.emit({ type: 'socket', connected: true }) }
    this.ws.onclose = () => { this.connected = false; this.emit({ type: 'socket', connected: false }); clearTimeout(this.timer); this.timer = setTimeout(() => this.connect(), 1500) }
    this.ws.onerror = () => this.ws?.close()
    this.ws.onmessage = (m) => { try { this.emit(JSON.parse(m.data)) } catch {} }
  }
  on(h: Handler) { this.handlers.add(h); return () => this.handlers.delete(h) }
  private emit(ev: any) { this.handlers.forEach(h => { try { h(ev) } catch (e) { console.error(e) } }) }
  send(obj: any) {
    const s = JSON.stringify(obj)
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(s)
    else { this.queue.push(s); this.connect() }
  }
}

export const chatSocket = new ChatSocket()
