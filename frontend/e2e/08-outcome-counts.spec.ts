import { expect, test } from '@playwright/test'
import { canvas, resetAll, setSessions } from './harness/api.js'
import { outcomeSessions, seedOutcomeGraph } from './harness/fixtures.js'

test.beforeEach(async ({ request }) => {
  await resetAll(request)
})

test('spec 8: outcome kinds show matching counts after refresh', async ({
  page,
  request,
}) => {
  const fixture = await seedOutcomeGraph(request)
  await setSessions(request, outcomeSessions())
  await page.goto('/')
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
    await expect(outcomes.nth(index)).toHaveAttribute('data-status', 'Ready')
  }
  await page.locator('[data-testid=refresh-invocations]').click()
  await expect(page.locator('.vue-flow__edge-text')).toContainText([
    '6 invocations',
    '2 outcomes',
    '2 outcomes',
    '1 outcome',
    '1 outcome',
  ])
  const saved = await canvas(request)
  expect(saved.action_nodes[0].invocation_count).toBe(6)
  expect(
    saved.edges
      .filter((edge) => edge.target.kind === 'outcome')
      .map((edge) => edge.outcome_count),
  ).toEqual([2, 2, 1, 1])
  expect(fixture.outcomeIds).toHaveLength(4)
})
