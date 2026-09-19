import type { NodeKind } from '@/lib/connectRules'

export const NODE_KINDS: readonly NodeKind[] = ['trigger', 'action', 'outcome']
export const NODE_KIND_MIME = 'application/x-devin-flow-node-kind'

export function isNodeKind(value: string): value is NodeKind {
  return NODE_KINDS.includes(value as NodeKind)
}

export function nodeLabel(kind: NodeKind): string {
  return kind[0].toUpperCase() + kind.slice(1)
}

export function nodeHint(kind: NodeKind): string {
  if (kind === 'trigger') return 'Choose repository and event'
  if (kind === 'action') return 'Choose a Playbook'
  return 'Choose an Outcome kind'
}

export function nodeAccentClass(kind: NodeKind): string {
  if (kind === 'trigger') return 'border-l-sky-500'
  if (kind === 'action') return 'border-l-violet-500'
  return 'border-l-emerald-500'
}
