import { expect, test } from '@playwright/test'
import { canvas, dragPalette, resetAll } from './harness/api.js'

test.beforeEach(async ({ request }) => {
  await resetAll(request)
})

test('spec 1: empty board loads and palette creates nodes', async ({
  page,
}) => {
  await page.goto('/')
  await expect(page.locator('[data-testid=api-status]')).toHaveText(
    'Polling off',
  )
  await expect(page.locator('[data-testid=palette-trigger]')).toBeVisible()
  await expect(page.locator('[data-testid=palette-action]')).toBeVisible()
  await expect(page.locator('[data-testid=palette-outcome]')).toBeVisible()
  await expect(page.locator('.vue-flow__node')).toHaveCount(0)

  await dragPalette(page, 'trigger', 180, 160)
  await dragPalette(page, 'action', 460, 160)
  await dragPalette(page, 'outcome', 740, 160)
  await expect(page.locator('[data-testid=canvas-node]')).toHaveCount(3)
  await expect(
    page.locator('[data-testid=canvas-node][data-kind=trigger]'),
  ).toHaveCount(1)
  await expect(
    page.locator('[data-testid=canvas-node][data-kind=action]'),
  ).toHaveCount(1)
  await expect(
    page.locator('[data-testid=canvas-node][data-kind=outcome]'),
  ).toHaveCount(1)

  const saved = await canvas()
  expect(saved.trigger_nodes).toHaveLength(1)
  expect(saved.action_nodes).toHaveLength(1)
  expect(saved.outcome_nodes).toHaveLength(1)
})
