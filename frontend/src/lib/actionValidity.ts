import type { components } from '@/api/schema'

export type ActionNodeRead = components['schemas']['ActionNodeRead']
export type ActionFields = {
  name: string
  playbookId: string | null
  prompt: string
}
export type ActionInvalidReason = 'incomplete' | 'no-trigger'
export type LinkedEdge = {
  target: string
  data?: { sourceKind?: string }
}

export function actionFieldsFromData(
  data: Record<string, unknown>,
): ActionFields {
  return {
    name: typeof data.name === 'string' ? data.name : '',
    playbookId: typeof data.playbookId === 'string' ? data.playbookId : null,
    prompt: typeof data.prompt === 'string' ? data.prompt : '',
  }
}

export function actionFieldsOf(node: ActionNodeRead): ActionFields {
  return {
    name: node.name,
    playbookId: node.playbook_id,
    prompt: node.prompt,
  }
}

export function isActionComplete(
  fields: Pick<ActionFields, 'name' | 'playbookId'>,
): boolean {
  return fields.name.trim() !== '' && fields.playbookId !== null
}

export function actionIncompleteHint(
  fields: Pick<ActionFields, 'name' | 'playbookId'>,
): string | null {
  const missingName = fields.name.trim() === ''
  const missingPlaybook = fields.playbookId === null
  if (missingName && missingPlaybook) {
    return 'Enter a name and choose a Playbook'
  }
  if (missingName) return 'Enter a name'
  if (missingPlaybook) return 'Choose a Playbook'
  return null
}

export function hasLinkedTrigger(nodeId: string, edges: LinkedEdge[]): boolean {
  return edges.some(
    (edge) => edge.target === nodeId && edge.data?.sourceKind === 'trigger',
  )
}

export function actionInvalidReason(
  nodeId: string,
  fields: Pick<ActionFields, 'name' | 'playbookId'>,
  edges: LinkedEdge[],
): ActionInvalidReason | null {
  if (!isActionComplete(fields)) return 'incomplete'
  if (!hasLinkedTrigger(nodeId, edges)) return 'no-trigger'
  return null
}
