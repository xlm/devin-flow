export type NodeKind = 'trigger' | 'action' | 'outcome'

export type CanvasEdge = {
  source: string
  target: string
}

type EdgeWithSourceKind = CanvasEdge & {
  sourceKind: NodeKind
}

const allowedPairs = new Set<string>(['trigger:action', 'action:outcome'])

export function kindOf(node: {
  data?: { kind?: NodeKind }
}): NodeKind | undefined {
  return node.data?.kind
}

export function connectError(
  source: { id: string; kind: NodeKind },
  target: { id: string; kind: NodeKind },
  edges: EdgeWithSourceKind[],
): string | null {
  if (!allowedPairs.has(`${source.kind}:${target.kind}`)) {
    return 'edges must connect a Trigger to an Action or an Action to an Outcome'
  }
  if (
    edges.some((edge) => edge.source === source.id && edge.target === target.id)
  ) {
    return 'these nodes are already connected'
  }
  if (
    source.kind === 'trigger' &&
    edges.some((edge) => edge.source === source.id)
  ) {
    return 'a Trigger can have only one outgoing edge'
  }
  if (
    target.kind === 'action' &&
    edges.some(
      (edge) => edge.target === target.id && edge.sourceKind === 'trigger',
    )
  ) {
    return 'an Action can have only one incoming Trigger edge'
  }
  return null
}
