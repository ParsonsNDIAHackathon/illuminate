const USER = 'local'

export class ApiError extends Error {
  status: number
  retryAfter: number
  constructor(message: string, status: number, retryAfter: number) {
    super(message)
    this.status = status
    this.retryAfter = retryAfter
  }
}

async function request<T = any>(method: string, path: string, body?: any): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-User': USER },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail ?? detail } catch {}
    throw new ApiError(`${method} ${path}: ${detail}`, r.status, Math.max(0, Number(r.headers.get('Retry-After')) || 0))
  }
  return r.json()
}

export const api = {
  get: <T = any>(p: string) => request<T>('GET', p),
  post: <T = any>(p: string, b?: any) => request<T>('POST', p, b ?? {}),
  put: <T = any>(p: string, b?: any) => request<T>('PUT', p, b ?? {}),
  del: <T = any>(p: string) => request<T>('DELETE', p),
}

export const qs = (o: Record<string, any>) =>
  Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '').map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&')
