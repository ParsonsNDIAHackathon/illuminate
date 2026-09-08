/** Prevent an older async request from committing after its scope has changed. */
export class LatestRequest {
  private generation = 0

  begin(): number {
    return ++this.generation
  }

  isCurrent(generation: number): boolean {
    return generation === this.generation
  }

  current(): number {
    return this.generation
  }
}

export type ScopedRowToken = { scope: number; row: number }

/** Keep scope replacement independent from concurrent retries on different rows. */
export class ScopedRowRequests<Key> {
  private readonly scope = new LatestRequest()
  private readonly rows = new Map<Key, LatestRequest>()

  beginScope(): number {
    this.rows.clear()
    return this.scope.begin()
  }

  currentScope(): number {
    return this.scope.current()
  }

  beginRow(key: Key, scope = this.currentScope()): ScopedRowToken {
    let request = this.rows.get(key)
    if (!request) {
      request = new LatestRequest()
      this.rows.set(key, request)
    }
    return { scope, row: request.begin() }
  }

  isCurrent(key: Key, token: ScopedRowToken): boolean {
    return this.scope.isCurrent(token.scope) && Boolean(this.rows.get(key)?.isCurrent(token.row))
  }
}