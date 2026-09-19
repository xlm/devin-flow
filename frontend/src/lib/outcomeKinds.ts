import type { OutcomeKind } from '@/lib/connectRules'

export const OUTCOME_KIND_LABELS: Record<OutcomeKind, string> = {
  pull_request: 'Pull Request',
  duplicate: 'Duplicate',
  not_reproducible: 'Not reproducible',
  not_a_bug: 'Not a bug',
}

export const OUTCOME_KINDS = Object.keys(OUTCOME_KIND_LABELS) as OutcomeKind[]

export function outcomeKindLabel(kind: OutcomeKind): string {
  return OUTCOME_KIND_LABELS[kind]
}

export function outcomeCountLabel(count: number): string {
  return `${count} ${count === 1 ? 'outcome' : 'outcomes'}`
}
