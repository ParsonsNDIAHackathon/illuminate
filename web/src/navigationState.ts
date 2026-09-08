export type QueryState = Record<string, unknown>

function value(query: QueryState, key: string) {
  const raw = query[key]
  return Array.isArray(raw) ? String(raw[0] || '') : String(raw || '')
}

export function claimScope(query: QueryState) {
  const requestedStatus = value(query, 'status')
  return {
    status: ['staged', 'committed', 'rejected'].includes(requestedStatus) ? requestedStatus : 'staged',
    entityId: value(query, 'entity_id'),
    programId: value(query, 'program_id') || value(query, 'root_id'),
    claimId: value(query, 'claim_id'),
  }
}

export function missionProgramFromQuery(query: QueryState, programs: Array<{ id: string }>) {
  const requested = value(query, 'root_id') || value(query, 'program')
  return programs.some(program => program.id === requested) ? requested : (programs[0]?.id || '')
}

export function reportRouteQuery(query: QueryState, fallbackRoot: string, vendor: string, overrides: QueryState = {}) {
  return {
    ...query,
    root_id: value(query, 'root_id') || fallbackRoot || undefined,
    vendor,
    ...overrides,
  }
}

export function missionRootFromQuery(query: QueryState, fallbackRoot = '') {
  return value(query, 'root_id') || fallbackRoot
}

export function createRequestGate() {
  let latest = 0
  return {
    begin() { return ++latest },
    current() { return latest },
    isCurrent(request: number) { return request === latest },
  }
}

export function createActiveRouteRequestGate(activeRouteName: string) {
  let latest = 0
  let mounted = false
  return {
    mount() { mounted = true },
    begin() { return ++latest },
    current() { return latest },
    isCurrent(request: number, routeName: unknown) {
      return mounted && routeName === activeRouteName && request === latest
    },
    unmount() {
      mounted = false
      latest++
    },
  }
}