import type { components } from '@/api/schema'

type Schemas = components['schemas']

export type NodeKind = Schemas['NodeRead']['kind']
export type Position = Schemas['Position']
export type NodeRef = Schemas['NodeRef']
export type NodeRead = Schemas['NodeRead']
export type EdgeRead = Schemas['EdgeRead']
export type EdgeCreate = Schemas['EdgeCreate']
export type TriggerRead = Schemas['TriggerRead']
export type TriggerUpdate = Schemas['TriggerUpdate']
export type EventAction = NonNullable<TriggerRead['event_action']>
export type OutcomeRead = Schemas['OutcomeRead']
export type OutcomeUpdate = Schemas['OutcomeUpdate']
export type OutcomeKind = NonNullable<OutcomeRead['kind']>
export type OutcomeInvocationRead = Schemas['OutcomeInvocationRead']

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
  source: NodeRef,
  target: NodeRef,
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
