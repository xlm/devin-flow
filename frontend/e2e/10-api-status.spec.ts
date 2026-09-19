import { expect, test } from '@playwright/test'
import { resetAll, startBackend, stopBackend } from './harness/api.js'
import { seedBasic } from './harness/fixtures.js'

test.beforeEach(async ({ request }) => {
  await resetAll(request)
})

test.afterEach(async ({ request }) => {
  await startBackend(request)
})

test('spec 10: status indicator tracks API health without a reload', async ({
  page,
  request,
}) => {
  await seedBasic()
  await page.goto('/')
  const status = page.locator('[data-testid=api-status]')
  // The E2E stack runs with POLL_INTERVAL_SECONDS=0.
  await expect(status).toHaveAttribute('data-tone', 'amber')
  await expect(status).toHaveText('Polling off')
  await expect(status).toHaveCSS('pointer-events', 'none')

  await stopBackend(request)
  // The next 15s health poll notices the outage.
  await expect(status).toHaveAttribute('data-tone', 'red', { timeout: 20_000 })
  await expect(status).toHaveText('API error')

  await startBackend(request)
  await page.locator('[data-testid=refresh-invocations]').click()
  await expect(status).toHaveAttribute('data-tone', 'amber')
  await expect(status).toHaveText('Polling off')
})

test('spec 10: Canvas retry refreshes the indicator', async ({
  page,
  request,
}) => {
  await seedBasic()
  await stopBackend(request)
  await page.goto('/')
  const status = page.locator('[data-testid=api-status]')
  await expect(page.locator('[data-testid=load-error]')).toBeVisible()
  await expect(status).toHaveAttribute('data-tone', 'red')

  await startBackend(request)
  await page.locator('[data-testid=load-retry]').click()
  await expect(page.locator('[data-testid=load-error]')).toBeHidden()
  await expect(status).toHaveAttribute('data-tone', 'amber')
  await expect(status).toHaveText('Polling off')
})
