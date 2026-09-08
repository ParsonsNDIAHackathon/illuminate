const SHARED_MODEL_CONNECTORS = new Set(['openai', 'websearch'])

export function isModelBackedConnector(name: string): boolean {
  return SHARED_MODEL_CONNECTORS.has(name)
}

export function invalidateConnectorResults<T>(results: Record<string, T>, name: string): Record<string, T> {
  const next = { ...results }
  if (isModelBackedConnector(name)) {
    for (const connector of SHARED_MODEL_CONNECTORS) delete next[connector]
  } else {
    delete next[name]
  }
  return next
}

export function recordConnectorResult<T>(results: Record<string, T>, name: string, result: T): Record<string, T> {
  return { ...results, [name]: result }
}