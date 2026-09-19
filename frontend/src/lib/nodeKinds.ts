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

export const NODE_HANDLES: Record<
  NodeKind,
  { target: boolean; source: boolean }
> = {
  trigger: { target: false, source: true },
  action: { target: true, source: true },
  outcome: { target: true, source: false },
}

export const NODE_KINDS: readonly NodeKind[] = Object.keys(KINDS) as NodeKind[]
export const NODE_KIND_MIME = 'application/x-devin-flow-node-kind'

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
