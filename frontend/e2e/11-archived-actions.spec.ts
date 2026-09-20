import { expect, test, type Page } from '@playwright/test'
import { apiClient, canvas, resetAll } from './harness/api.js'
import { seedConfigured } from './harness/fixtures.js'
import { ARCHIVED_ACTION_MIME } from '../src/lib/nodeKinds.js'

test.beforeEach(async ({ request }) => {
  await resetAll(request)
})

async function archiveAction(actionId: string): Promise<void> {
  const { error } = await apiClient.DELETE(
    '/api/canvas/nodes/{kind}/{node_id}',
    {
      params: { path: { kind: 'action', node_id: actionId } },
    },
  )
  if (error) throw new Error('archive action failed')
}

async function dragArchivedRow(
  page: Page,
  actionId: string,
  x: number,
  y: number,
): Promise<void> {
  const row = page.locator(
    `[data-testid="archived-action"][data-id="${actionId}"]`,
  )
  const dropZone = page.locator('[data-testid="canvas-drop-zone"]')
  try {
    await row.dragTo(dropZone, { targetPosition: { x, y } })
  } catch {
    await page.evaluate(
      ({ id, x: clientX, y: clientY, mime }) => {
        const source = document.querySelector(
          `[data-testid="archived-action"][data-id="${id}"]`,
        )
        const target = document.querySelector(
          '[data-testid="canvas-drop-zone"]',
        )
        if (!source || !target)
          throw new Error('archived row or drop zone is missing')
        const transfer = new DataTransfer()
        transfer.setData(mime, id)
        source.dispatchEvent(
          new DragEvent('dragstart', { dataTransfer: transfer }),
        )
        target.dispatchEvent(
          new DragEvent('dragover', {
            bubbles: true,
            clientX,
            clientY,
            dataTransfer: transfer,
          }),
        )
        target.dispatchEvent(
          new DragEvent('drop', {
            bubbles: true,
            clientX,
            clientY,
            dataTransfer: transfer,
          }),
        )
      },
      { id: actionId, x, y, mime: ARCHIVED_ACTION_MIME },
    )
  }
}

test('spec 11: an archived Action restores from the sheet', async ({
  page,
}) => {
  const fixture = await seedConfigured()
  await archiveAction(fixture.actionId)
  await page.goto('/')
  await expect(page.locator('.vue-flow__node')).toHaveCount(1)
  await page.getByTestId('archived-actions-button').click()
  const row = page.getByTestId('archived-action')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('Triage issue')
  await expect(row).toContainText('pb-triage')
  await row.getByTestId('archived-restore').click()
  await expect(
    page.locator(`.vue-flow__node[data-id="${fixture.actionId}"]`),
  ).toBeVisible()
  await expect(page.getByTestId('archived-empty')).toBeVisible()
  const saved = await canvas()
  expect(saved.action_nodes.map((action) => action.id)).toEqual([
    fixture.actionId,
  ])
  await page.reload()
  await expect(page.locator('.vue-flow__node')).toHaveCount(2)
})

test('spec 11: dragging an archived Action restores it at the drop point', async ({
  page,
}) => {
  const fixture = await seedConfigured()
  await archiveAction(fixture.actionId)
  await page.goto('/')
  await page.getByTestId('archived-actions-button').click()
  const row = page.getByTestId('archived-action')
  await expect(row).toHaveCount(1)
  await dragArchivedRow(page, fixture.actionId, 300, 300)
  await expect(
    page.locator(`.vue-flow__node[data-id="${fixture.actionId}"]`),
  ).toBeVisible()
  await expect(page.getByTestId('archived-empty')).toBeVisible()
  const saved = await canvas()
  expect(saved.action_nodes.map((action) => action.id)).toEqual([
    fixture.actionId,
  ])
})
