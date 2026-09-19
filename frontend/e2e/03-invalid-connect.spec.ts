import { expect, test } from '@playwright/test'
import {
  canvas,
  connect,
  createNode,
  resetAll,
  trackRequests,
} from './harness/api.js'
import { seedBasic } from './harness/fixtures.js'

test.beforeEach(async ({ request }) => {
  await resetAll(request)
})

test('spec 3: forbidden and duplicate connections are refused client-side', async ({
  page,
  request,
}) => {
  const fixture = await seedBasic(request)
  const outcome = await createNode(request, 'outcome', { x: 800, y: 180 })
  await page.goto('/')
  const requests = trackRequests(page)
  await connect(page, fixture.triggerId, outcome.id)
  await connect(page, fixture.triggerId, fixture.actionId)
  await expect(page.locator('.vue-flow__edge')).toHaveCount(1)
  expect(
    requests.filter(
      (item) =>
        item.method === 'POST' && item.url.endsWith('/api/canvas/edges'),
    ),
  ).toHaveLength(0)
  expect((await canvas(request)).edges).toHaveLength(1)
})
