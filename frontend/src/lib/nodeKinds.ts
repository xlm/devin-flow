import type { NodeKind } from '@/lib/connectRules'

const KINDS: Record<NodeKind, true> = {
  trigger: true,
  action: true,
  outcome: true,
}

const NODE_HINTS: Record<NodeKind, string> = {
  trigger: 'Choose repository and event',
  action: 'Choose a Playbook',
  outcome: 'Choose an Outcome kind',
}

const NODE_ACCENT_CLASSES: Record<NodeKind, string> = {
  trigger: 'border-l-sky-500',
  action: 'border-l-violet-500',
  outcome: 'border-l-emerald-500',
}

export type HandleSide = 'source' | 'target'

export const NODE_HANDLES: Record<
  NodeKind,
  { target: boolean; source: boolean }
> = {
  trigger: { target: false, source: true },
  action: { target: true, source: true },
  outcome: { target: true, source: false },
}

// A connection takes the colour of the kind it flows out of, so a target
// handle is coloured after the kind that connects into it.
const HANDLE_COLOR_KINDS: Record<NodeKind, Record<HandleSide, NodeKind>> = {
  trigger: { source: 'trigger', target: 'trigger' },
  action: { source: 'action', target: 'trigger' },
  outcome: { source: 'outcome', target: 'action' },
}

const HANDLE_CLASSES: Record<NodeKind, string> = {
  trigger: 'bg-sky-500!',
  action: 'bg-violet-500!',
  outcome: 'bg-emerald-500!',
}

export const NODE_KINDS: readonly NodeKind[] = Object.keys(KINDS) as NodeKind[]
export const NODE_KIND_MIME = 'application/x-devin-flow-node-kind'
export const ARCHIVED_ACTION_MIME = 'application/x-devin-flow-archived-action'

export function isNodeKind(value: string): value is NodeKind {
  return NODE_KINDS.includes(value as NodeKind)
}

export function nodeLabel(kind: NodeKind): string {
  return kind[0].toUpperCase() + kind.slice(1)
}

export function nodeHint(kind: NodeKind): string {
  return NODE_HINTS[kind]
}

export function nodeAccentClass(kind: NodeKind): string {
  return NODE_ACCENT_CLASSES[kind]
}

export function nodeHandleClass(kind: NodeKind, side: HandleSide): string {
  return HANDLE_CLASSES[HANDLE_COLOR_KINDS[kind][side]]
}
