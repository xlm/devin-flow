import { expect, test } from '@playwright/test'
import {
  canvas,
  resetAll,
  setSessions,
  startBackend,
  stopBackend,
} from './harness/api.js'
import {
  outcomeSessions,
  seedConfigured,
  seedOutcomeGraph,
  triggerSessions,
} from './harness/fixtures.js'

async function chooseKinds(
  page: import('@playwright/test').Page,
): Promise<void> {
  const outcomes = page.locator('[data-testid=canvas-node][data-kind=outcome]')
  for (const [index, kind] of [
    'pull_request',
    'duplicate',
    'not_reproducible',
    'not_a_bug',
  ].entries()) {
    await outcomes
      .nth(index)
      .locator('[data-testid=outcome-kind]')
      .selectOption(kind)
  }
  await page.locator('[data-testid=refresh-invocations]').click()
}

async function clickOutcomeEdge(
  page: import('@playwright/test').Page,
  label: string,
  index = 0,
): Promise<void> {
  await page
    .locator('.vue-flow__edge')
    .filter({ hasText: label })
    .nth(index)
    .locator('.vue-flow__edge-textwrapper')
    .click({ force: true })
}

test.beforeEach(async ({ request }) => {
  await resetAll(request)
})

test('spec 9: Action -> Pull Request edge opens the Invocation sheet', async ({
  page,
  request,
}) => {
  await seedOutcomeGraph()
  await setSessions(request, outcomeSessions())
  await page.goto('/')
  await clickOutcomeEdge(page, '0 outcomes')
  const sheet = page.locator('[data-testid=outcome-sheet], [role=dialog]')
  await expect(sheet.locator('[data-testid=outcome-invocation]')).toHaveCount(0)
  await expect(sheet.locator('[data-testid=outcome-empty]')).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()
  await expect(sheet).toBeHidden()
  await chooseKinds(page)
  await clickOutcomeEdge(page, '2 outcomes')
  await expect(sheet.locator('[data-testid=outcome-invocation]')).toHaveCount(2)
  await expect(
    sheet.locator('[data-testid=outcome-invocation]').nth(0),
  ).toContainText('Open pull request duplicate')
  await expect(
    sheet.locator('[data-testid=outcome-invocation]').nth(1),
  ).toContainText('Merged pull request')
  await expect(
    sheet.locator('a[href="https://app.devin.ai/sessions/s-both"]'),
  ).toBeVisible()
  await expect(
    sheet.locator('a[href="https://github.com/acme/widgets/pull/2"]'),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()
  await expect(sheet).toBeHidden()

  await clickOutcomeEdge(page, '2 outcomes', 1)
  await expect(sheet.locator('[data-testid=outcome-invocation]')).toHaveCount(2)
  await expect(
    sheet.locator('[data-testid=outcome-invocation]').nth(0),
  ).toContainText('Open pull request duplicate')
  await expect(
    sheet.locator('[data-testid=outcome-invocation]').nth(1),
  ).toContainText('Duplicate issue')
  await expect(
    sheet.locator('a[href="https://github.com/acme/widgets/issues/2"]'),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()
  await expect(sheet).toBeHidden()

  await clickOutcomeEdge(page, '1 outcome')
  await expect(sheet.locator('[data-testid=outcome-invocation]')).toHaveCount(1)
  await expect(sheet).toContainText('Not reproducible')
  await page.getByRole('button', { name: 'Close' }).click()
  await expect(sheet).toBeHidden()

  await clickOutcomeEdge(page, '1 outcome', 1)
  await expect(sheet.locator('[data-testid=outcome-invocation]')).toHaveCount(1)
  await expect(sheet).toContainText('Not a bug')
  await page.getByRole('button', { name: 'Close' }).click()
  await expect(sheet).toBeHidden()
  expect((await canvas()).edges).toHaveLength(5)
})

test('spec 9: Trigger -> Action edge count opens the Invocation sheet', async ({
  page,
  request,
}) => {
  await seedConfigured()
  await setSessions(request, triggerSessions())
  await page.goto('/')
  const edge = page.locator('.vue-flow__edge').filter({ hasText: 'invocation' })
  const sheet = page.locator('[data-testid=action-sheet], [role=dialog]')
  const rows = sheet.locator('[data-testid=action-invocation]')

  await edge.locator('.vue-flow__edge-textwrapper').click({ force: true })
  await expect(sheet).toContainText('Triage issue invocations')
  await expect(rows).toHaveCount(0)
  await expect(sheet.locator('[data-testid=action-empty]')).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()
  await expect(sheet).toBeHidden()

  await page.locator('[data-testid=refresh-invocations]').click()
  await expect(edge.locator('.vue-flow__edge-text')).toContainText(
    '3 invocations',
  )
  await edge.locator('.vue-flow__edge-text').click({ force: true })
  await expect(rows).toHaveCount(3)
  await expect(rows.nth(0)).toContainText('Issue unknown')
  await expect(rows.nth(0)).toContainText('Manual run')
  await expect(rows.nth(1)).toContainText('#12')
  await expect(rows.nth(1)).toContainText('running')
  await expect(
    rows.nth(1).locator('a[href="https://github.com/acme/widgets/issues/12"]'),
  ).toBeVisible()
  await expect(rows.nth(2)).toContainText('#40 Login button unresponsive')
  await expect(
    rows.nth(2).locator('a[href="https://github.com/acme/widgets/issues/40"]'),
  ).toBeVisible()
  await expect(
    rows.nth(2).locator('a[href="https://app.devin.ai/sessions/s-issue"]'),
  ).toBeVisible()
  await expect(
    rows.nth(2).locator('a[href="https://github.com/acme/widgets/pull/40"]'),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()
  await expect(sheet).toBeHidden()

  await stopBackend(request)
  await edge.locator('.vue-flow__edge-textwrapper').click({ force: true })
  await expect(sheet.locator('[data-testid=action-error]')).toBeVisible()
  await expect(rows).toHaveCount(0)
  await startBackend(request)
  await sheet.locator('[data-testid=action-retry]').click()
  await expect(sheet.locator('[data-testid=action-error]')).toBeHidden()
  await expect(rows).toHaveCount(3)
  await page.getByRole('button', { name: 'Close' }).click()
  await expect(sheet).toBeHidden()
  expect((await canvas()).action_nodes[0].invocation_count).toBe(3)
})

test('spec 9: edge paths select without opening sheets', async ({ page }) => {
  await seedOutcomeGraph()
  await page.goto('/')
  const edge = page
    .locator('.vue-flow__edge')
    .filter({ hasText: '0 outcomes' })
    .first()
  const sheet = page.locator('[data-testid=outcome-sheet], [role=dialog]')

  await edge.locator('path.vue-flow__edge-path').first().dispatchEvent('click')
  await expect(edge).toHaveClass(/selected/)
  await expect(sheet).not.toBeVisible()

  await edge.locator('.vue-flow__edge-textwrapper').click({ force: true })
  await expect(sheet).toBeVisible()
})
