/**
 * Which layers this browser draws.
 *
 * A layer choice is a property of the screen someone is looking at, not of the workspace: it
 * is how one person makes one canvas readable, so it belongs beside the theme and the depth,
 * in localStorage, and not in the workspace file every user of the app shares. The server
 * still keeps a copy — a tool call that arrives carrying no layers has to fall back on
 * something — but what the canvas draws is whatever this browser last chose.
 */

export const LAYERS_KEY = 'illuminate.layers'

/** Every optional layer off. The canvas opens on the program and the chain of contracts and
 *  ownership around it — entities, which are always drawn — and nothing else; each layer over
 *  that is a deliberate "show me this too". Indirect orgs are off with the rest: a prime brings
 *  in hundreds of trade councils, lobbying counterparties and sister companies that no award
 *  touches, and they are the single biggest thing between a user and a readable graph. Anything
 *  scored over the risk pin floor is drawn whatever the toggles say, so an off layer is never
 *  how a designated party disappears (see graphLayers.ts). */
export const LAYERS_OFF: Record<string, boolean> = {
  entities: true,
  indirect_orgs: false,
  people: false,
  countries: false,
  categories: false,
  artifacts: false,
  sources: false,
  claims: false,
  reports: false,
}

/** This browser's choices, or the defaults. Storage can fail outright — a private window, a
 *  browser set to block site data — and can hold something another version of the app wrote, so
 *  every path here ends at a usable map rather than an exception. */
export function readLayers(): Record<string, boolean> {
  try {
    const saved = localStorage.getItem(LAYERS_KEY)
    // Spread over the defaults so a layer added since this browser last saved arrives off
    // rather than undefined.
    return saved ? { ...LAYERS_OFF, ...JSON.parse(saved) } : { ...LAYERS_OFF }
  } catch {
    return { ...LAYERS_OFF }
  }
}

/** Remember the choices. A failure here costs the next visit, not this one, so it is swallowed:
 *  the toggle the user just clicked still holds for the session. */
export function writeLayers(layers: Record<string, boolean>): void {
  try {
    localStorage.setItem(LAYERS_KEY, JSON.stringify(layers))
  } catch {
    /* nothing to do and nothing worth interrupting the user over */
  }
}
