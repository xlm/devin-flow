import { expect, test } from '@playwright/test'
import { canvas, connect, resetAll } from './harness/api.js'
import { seedBasic } from './harness/fixtures.js'

test.beforeEach(async ({ request }) => {
  await resetAll(request)
})

test('spec 2: connected edge persists across reload', async ({
  page,
  request,
}) => {
  const fixture = await seedBasic(request)
  await page.goto('/')
  await connect(page, fixture.triggerId, fixture.actionId)
  await expect(page.locator('.vue-flow__edge')).toHaveCount(1)
  await expect(page.locator('.vue-flow__edge-text')).toHaveText('0 invocations')
  expect((await canvas(request)).edges).toHaveLength(1)

  await page.reload()
  await expect(page.locator('.vue-flow__edge')).toHaveCount(1)
  await expect(page.locator('.vue-flow__edge-text')).toHaveText('0 invocations')
})
