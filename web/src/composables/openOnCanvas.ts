import { useRouter } from 'vue-router'
import { useGraph } from '../stores/graph'
import { useWorkspace } from '../stores/workspace'

/**
 * Put one party on the canvas, selected, and go there. A list row or a page opens the
 * node's page by default; this is the other door, the one that shows it in context.
 *
 * A person hidden by the people layer would arrive and not be drawn, so opening a person
 * turns the layer on: the user asked to see this node.
 */
export function useOpenOnCanvas() {
  const router = useRouter(); const graph = useGraph(); const ws = useWorkspace()

  async function openOnCanvas(id: string, label?: string | null) {
    if (!ws.loaded) await ws.load()
    if (label === 'Person' && !ws.ws.layers.people) ws.setLayer('people', true)
    if (!graph.nodes.has(id)) await graph.loadNeighbourhood(id, ws.depth, ws.ws.layers)
    graph.select(id)
    router.push('/')
  }

  return { openOnCanvas }
}
