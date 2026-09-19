import { expect, test } from '@playwright/test'
import { canvas, resetAll, startBackend, stopBackend } from './harness/api.js'
import { seedBasic } from './harness/fixtures.js'

test.beforeEach(async ({ request }) => {
  await resetAll(request)
})

test('spec 7: Canvas retry restores a graph after backend recovery', async ({
  page,
  request,
}) => {
  await seedBasic()
  await stopBackend(request)
  await page.goto('/')
  await expect(page.locator('[data-testid=load-error]')).toBeVisible()
  await expect(page.locator('[data-testid=load-retry]')).toBeVisible()
  await expect(page.locator('.vue-flow__node')).toHaveCount(0)
  await startBackend(request)
  await page.locator('[data-testid=load-retry]').click()
  await expect(page.locator('[data-testid=load-error]')).toBeHidden()
  await expect(page.locator('.vue-flow__node')).toHaveCount(2)
  await expect(page.locator('.vue-flow__edge')).toHaveCount(1)
  expect((await canvas()).edges).toHaveLength(1)
})
