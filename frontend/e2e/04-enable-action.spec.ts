import { expect, test } from '@playwright/test'
import { calls, canvas, resetAll } from './harness/api.js'
import { seedBasic } from './harness/fixtures.js'

test.beforeEach(async ({ request }) => {
  await resetAll(request)
})

test('spec 4: configuring and enabling an Action provisions automation', async ({
  page,
  request,
}) => {
  const fixture = await seedBasic()
  await page.goto('/')
  const trigger = page.locator(
    `.vue-flow__node[data-id="${fixture.triggerId}"]`,
  )
  const action = page.locator(`.vue-flow__node[data-id="${fixture.actionId}"]`)
  const patch = (kind: string, id: string) =>
    page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/canvas/nodes/${kind}/${id}`) &&
        response.request().method() === 'PATCH',
    )
  await Promise.all([
    patch('trigger', fixture.triggerId),
    trigger.locator('[data-testid=trigger-event]').selectOption('opened'),
  ])
  await Promise.all([
    patch('trigger', fixture.triggerId),
    trigger
      .locator('[data-testid=trigger-repository]')
      .selectOption('acme/widgets'),
  ])
  const name = action.locator('[data-testid=action-name]')
  await name.fill('Triage issue')
  await Promise.all([
    patch('action', fixture.actionId),
    name.dispatchEvent('change'),
  ])
  await Promise.all([
    patch('action', fixture.actionId),
    action.locator('[data-testid=action-playbook]').selectOption('pb-triage'),
  ])
  await action.click()
  const enableSwitch = page.locator('[data-testid=enable-switch]')
  await expect(enableSwitch).toBeEnabled()
  const edge = page.locator('.vue-flow__edge')
  await expect(edge).toHaveCount(1)
  await expect(edge).not.toHaveClass(/animated/)
  await enableSwitch.click()
  await expect(
    action.locator('[data-testid=sync-badge][data-sync-status=enabled]'),
  ).toBeVisible()
  await expect(edge).toHaveClass(/animated/)

  const automationCalls = (await calls(request)).filter(
    (call) => call.method === 'POST' && call.path.endsWith('/automations'),
  )
  expect(automationCalls).toHaveLength(1)
  expect(automationCalls[0].authorization).toBe('Bearer e2e-fake-token')
  const body = automationCalls[0].body as {
    metadata: Record<string, string>
  }
  expect(body.metadata.devin_flow_action_id).toBe(fixture.actionId)
  const updates = (await calls(request)).filter(
    (call) =>
      call.method === 'PATCH' && call.path.endsWith('/automations/auto-1'),
  )
  expect(updates.at(-1)?.body).toMatchObject({ enabled: true })
  const saved = await canvas()
  expect(saved.action_nodes[0].automation_id).toBe('auto-1')
  expect(saved.action_nodes[0].sync_status).toBe('enabled')
  await page.reload()
  await expect(edge).toHaveClass(/animated/)
  await action.click()
  await expect(enableSwitch).toHaveText('Disable')
  await enableSwitch.click()
  await expect(
    action.locator('[data-testid=sync-badge][data-sync-status=disabled]'),
  ).toBeVisible()
  await expect(edge).not.toHaveClass(/animated/)
})
