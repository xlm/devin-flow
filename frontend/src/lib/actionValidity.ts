import type { components } from '@/api/schema'

export type ActionNodeRead = components['schemas']['ActionNodeRead']
export type ActionFields = {
  name: string
  playbookId: string | null
  prompt: string
  enabled: boolean
}
export type SyncStatus = ActionNodeRead['sync_status']
export type ActionInvalidReason =
  'incomplete' | 'no-trigger' | 'trigger-incomplete'
export type LinkedEdge = {
  source: string
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
    enabled: typeof data.enabled === 'boolean' ? data.enabled : false,
  }
}

export function actionFieldsOf(node: ActionNodeRead): ActionFields {
  return {
    name: node.name,
    playbookId: node.playbook_id,
    prompt: node.prompt,
    enabled: node.enabled,
  }
}

export function syncStateFromData(data: Record<string, unknown>): {
  status: SyncStatus
  error: string | null
} {
  const statuses: SyncStatus[] = [
    'unprovisioned',
    'pending',
    'enabled',
    'disabled',
    'error',
  ]
  const status = statuses.includes(data.syncStatus as SyncStatus)
    ? (data.syncStatus as SyncStatus)
    : 'unprovisioned'
  return {
    status,
    error: typeof data.syncError === 'string' ? data.syncError : null,
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
  triggerOf: (nodeId: string) => Record<string, unknown> | undefined,
): ActionInvalidReason | null {
  if (!isActionComplete(fields)) return 'incomplete'
  const triggerEdge = edges.find(
    (edge) => edge.target === nodeId && edge.data?.sourceKind === 'trigger',
  )
  if (!triggerEdge) return 'no-trigger'
  const trigger = triggerOf(triggerEdge.source)?.trigger
  if (typeof trigger !== 'object' || trigger === null) {
    return 'trigger-incomplete'
  }
  const triggerData = trigger as Record<string, unknown>
  if (
    typeof triggerData.event_action !== 'string' ||
    triggerData.event_action.trim() === '' ||
    typeof triggerData.repository_full_name !== 'string' ||
    triggerData.repository_full_name.trim() === ''
  ) {
    return 'trigger-incomplete'
  }
  return null
}
