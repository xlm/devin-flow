import { expect, test } from '@playwright/test'
import { canvas, resetAll, setSessions } from './harness/api.js'
import { seedConfigured, type BasicFixture } from './harness/fixtures.js'

test.beforeEach(async ({ request }) => {
  await resetAll(request)
})

async function refresh(page: import('@playwright/test').Page): Promise<void> {
  const response = page.waitForResponse(
    (item) =>
      item.request().method() === 'POST' &&
      new URL(item.url()).pathname === '/api/invocations/refresh',
  )
  await page.locator('[data-testid=refresh-invocations]').click()
  await response
}

test('spec 5: Refresh keeps the edge and invocation count', async ({
  page,
  request,
}) => {
  const fixture: BasicFixture = await seedConfigured(request)
  const now = Math.floor(Date.now() / 1000)
  await setSessions(request, [
    {
      session_id: 's-one',
      status: 'exit',
      title: 'First',
      url: 'https://app.devin.ai/sessions/s-one',
      automation_id: 'auto-1',
      created_at: now - 60,
      updated_at: now - 60,
    },
    {
      session_id: 's-two',
      status: 'exit',
      title: 'Second',
      url: 'https://app.devin.ai/sessions/s-two',
      automation_id: 'auto-1',
      created_at: now - 30,
      updated_at: now - 30,
    },
  ])
  await page.goto('/')
  const action = page.locator(`.vue-flow__node[data-id="${fixture.actionId}"]`)
  await expect(action).toBeVisible()
  await refresh(page)
  await expect(page.locator('.vue-flow__edge')).toHaveCount(1)
  await expect(page.locator('.vue-flow__edge-text')).toHaveText('2 invocations')
  expect((await canvas(request)).action_nodes[0].invocation_count).toBe(2)
  await page.waitForTimeout(600)
  await refresh(page)
  await expect(page.locator('.vue-flow__edge')).toHaveCount(1)
  await expect(page.locator('.vue-flow__edge-text')).toHaveText('2 invocations')
  expect((await canvas(request)).action_nodes[0].invocation_count).toBe(2)
})
