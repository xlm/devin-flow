import type { APIRequestContext } from '@playwright/test'
import { createEdge, createNode, type NodeKind, type Session } from './api.js'

export type BasicFixture = {
  triggerId: string
  actionId: string
}

export type OutcomeFixture = BasicFixture & {
  outcomeIds: string[]
}

const positions: Record<NodeKind, { x: number; y: number }> = {
  trigger: { x: 80, y: 180 },
  action: { x: 420, y: 180 },
  outcome: { x: 800, y: 80 },
}

export async function seedBasic(
  request: APIRequestContext,
): Promise<BasicFixture> {
  const trigger = await createNode(request, 'trigger', positions.trigger)
  const action = await createNode(request, 'action', positions.action)
  await createEdge(
    request,
    { id: trigger.id, kind: 'trigger' },
    { id: action.id, kind: 'action' },
  )
  return { triggerId: trigger.id, actionId: action.id }
}

export async function configureEnabled(
  request: APIRequestContext,
  fixture: BasicFixture,
): Promise<void> {
  const triggerResponse = await request.patch(
    `/api/canvas/nodes/trigger/${fixture.triggerId}`,
    {
      data: {
        trigger: {
          event_action: 'opened',
          repository_full_name: 'acme/widgets',
        },
      },
    },
  )
  if (!triggerResponse.ok()) throw new Error('failed to configure trigger')
  const fields = await request.patch(
    `/api/canvas/nodes/action/${fixture.actionId}`,
    {
      data: {
        name: 'Triage issue',
        playbook_id: 'pb-triage',
        prompt: 'Triage it.',
      },
    },
  )
  if (!fields.ok()) throw new Error('failed to configure action')
  const enabled = await request.patch(
    `/api/canvas/nodes/action/${fixture.actionId}`,
    {
      data: { enabled: true },
    },
  )
  if (!enabled.ok()) throw new Error('failed to enable action')
}

export async function seedConfigured(
  request: APIRequestContext,
): Promise<BasicFixture> {
  const fixture = await seedBasic(request)
  await configureEnabled(request, fixture)
  return fixture
}

export async function seedOutcomeGraph(
  request: APIRequestContext,
): Promise<OutcomeFixture> {
  const fixture = await seedConfigured(request)
  const outcomeIds: string[] = []
  for (let index = 0; index < 4; index += 1) {
    const outcome = await createNode(request, 'outcome', {
      x: positions.outcome.x,
      y: positions.outcome.y + index * 170,
    })
    outcomeIds.push(outcome.id)
    await createEdge(
      request,
      { id: fixture.actionId, kind: 'action' },
      { id: outcome.id, kind: 'outcome' },
    )
  }
  return { ...fixture, outcomeIds }
}

export function outcomeSessions(
  now = Math.floor(Date.now() / 1000),
): Session[] {
  return [
    {
      session_id: 's-pr',
      status: 'exit',
      title: 'Merged pull request',
      url: 'https://app.devin.ai/sessions/s-pr',
      automation_id: 'auto-1',
      pull_requests: [
        {
          pr_url: 'https://github.com/acme/widgets/pull/1',
          pr_state: 'merged',
        },
      ],
      structured_output: { outcome: 'fixed' },
      created_at: now - 300,
      updated_at: now - 300,
    },
    {
      session_id: 's-dup',
      status: 'exit',
      title: 'Duplicate issue',
      url: 'https://app.devin.ai/sessions/s-dup',
      automation_id: 'auto-1',
      structured_output: {
        outcome: 'duplicate',
        duplicate_of: 'https://github.com/acme/widgets/issues/1',
      },
      created_at: now - 240,
      updated_at: now - 240,
    },
    {
      session_id: 's-both',
      status: 'exit',
      title: 'Open pull request duplicate',
      url: 'https://app.devin.ai/sessions/s-both',
      automation_id: 'auto-1',
      pull_requests: [
        {
          pr_url: 'https://github.com/acme/widgets/pull/2',
          pr_state: 'open',
        },
      ],
      structured_output: {
        outcome: 'duplicate',
        duplicate_of: 'https://github.com/acme/widgets/issues/2',
      },
      created_at: now - 180,
      updated_at: now - 180,
    },
    {
      session_id: 's-nrep',
      status: 'exit',
      title: 'Not reproducible',
      url: 'https://app.devin.ai/sessions/s-nrep',
      automation_id: 'auto-1',
      structured_output: { outcome: 'not_reproducible' },
      created_at: now - 120,
      updated_at: now - 120,
    },
    {
      session_id: 's-nbug',
      status: 'exit',
      title: 'Not a bug',
      url: 'https://app.devin.ai/sessions/s-nbug',
      automation_id: 'auto-1',
      structured_output: { outcome: 'not_a_bug' },
      created_at: now - 60,
      updated_at: now - 60,
    },
    {
      session_id: 's-none',
      status: 'exit',
      title: 'No outcome',
      url: 'https://app.devin.ai/sessions/s-none',
      automation_id: 'auto-1',
      created_at: now,
      updated_at: now,
    },
  ]
}
