import { expect, test } from '@playwright/test'
import {
  canvas,
  createEdge,
  createNode,
  resetAll,
  trackRequests,
} from './harness/api.js'
import { seedBasic } from './harness/fixtures.js'

test.beforeEach(async ({ request }) => {
  await resetAll(request)
})

test('spec 6: deleting an Action cascades its edges', async ({
  page,
  request,
}) => {
  const fixture = await seedBasic(request)
  const outcome = await createNode(request, 'outcome', { x: 800, y: 180 })
  await createEdge(
    request,
    { id: fixture.actionId, kind: 'action' },
    { id: outcome.id, kind: 'outcome' },
  )
  await page.goto('/')
  const requests = trackRequests(page)
  await page.locator(`.vue-flow__node[data-id="${fixture.actionId}"]`).click()
  await page.keyboard.press('Backspace')
  await expect(page.locator('.vue-flow__node')).toHaveCount(2)
  await expect(page.locator('.vue-flow__edge')).toHaveCount(0)
  expect(
    requests.filter(
      (item) =>
        item.method === 'DELETE' &&
        item.url.includes('/api/canvas/nodes/action/'),
    ),
  ).toHaveLength(1)
  expect(
    requests.filter(
      (item) =>
        item.method === 'DELETE' && item.url.includes('/api/canvas/edges/'),
    ),
  ).toHaveLength(0)
  const saved = await canvas(request)
  expect(saved.action_nodes).toHaveLength(0)
  expect(saved.edges).toHaveLength(0)
  await page.reload()
  await expect(page.locator('.vue-flow__node')).toHaveCount(2)
  await expect(page.locator('.vue-flow__edge')).toHaveCount(0)
})
