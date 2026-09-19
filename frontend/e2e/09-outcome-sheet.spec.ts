import { expect, test } from '@playwright/test'
import { canvas, resetAll, setSessions } from './harness/api.js'
import { outcomeSessions, seedOutcomeGraph } from './harness/fixtures.js'

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

test('spec 9: Trigger -> Action edge count opens the Invocation sheet', async () => {
  test.skip(
    true,
    'TODO(#40): Trigger -> Action edge sheet is not implemented yet',
  )
})
