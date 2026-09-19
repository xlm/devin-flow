import type { APIRequestContext, Page } from '@playwright/test'
import createClient from 'openapi-fetch'
import type { components, paths } from '../../src/api/schema.js'

export type NodeKind = components['schemas']['NodeRef']['kind']
export type Position = components['schemas']['Position']
export type NodeRef = components['schemas']['NodeRef']
export type Session = {
  // DevinSession is an upstream payload, not part of our OpenAPI schema.
  session_id: string
  status: string
  title?: string
  url?: string
  automation_id?: string
  pull_requests?: Array<{ pr_url: string; pr_state?: string }>
  structured_output?: Record<string, unknown> | null
  created_at?: number
  updated_at?: number
}
export type Canvas = components['schemas']['CanvasRead']
type NodeRead =
  components['schemas']['ActionNodeRead'] | components['schemas']['NodeRead']

export const apiClient = createClient<paths>({
  baseUrl: 'http://127.0.0.1:5174',
})

export async function canvas(request: APIRequestContext): Promise<Canvas> {
  void request
  const { data, error } = await apiClient.GET('/api/canvas')
  if (error || !data) throw new Error('canvas request failed')
  return data
}

export async function createNode(
  request: APIRequestContext,
  kind: NodeKind,
  position: Position,
  body: Omit<components['schemas']['NodeCreate'], 'position'> = {},
): Promise<NodeRead> {
  void request
  const { data, error } = await apiClient.POST('/api/canvas/nodes/{kind}', {
    params: { path: { kind } },
    body: { position, ...body },
  })
  if (error || !data) throw new Error(`create ${kind} failed`)
  return data
}

export async function createEdge(
  request: APIRequestContext,
  source: NodeRef,
  target: NodeRef,
): Promise<void> {
  void request
  const { error } = await apiClient.POST('/api/canvas/edges', {
    body: { source, target },
  })
  if (error) throw new Error('create edge failed')
}

export async function setSessions(
  request: APIRequestContext,
  sessions: Session[],
): Promise<void> {
  const stub = process.env.E2E_STUB_URL
  if (!stub) throw new Error('E2E_STUB_URL is not set')
  const response = await request.put(`${stub}/_harness/sessions`, {
    data: sessions,
  })
  if (!response.ok())
    throw new Error(`set sessions failed: ${response.status()}`)
}

export async function calls(
  request: APIRequestContext,
): Promise<Array<Record<string, unknown>>> {
  const stub = process.env.E2E_STUB_URL
  if (!stub) throw new Error('E2E_STUB_URL is not set')
  const response = await request.get(`${stub}/_harness/calls`)
  return (await response.json()) as Array<Record<string, unknown>>
}

export async function resetAll(request: APIRequestContext): Promise<void> {
  const stub = process.env.E2E_STUB_URL
  if (!stub) throw new Error('E2E_STUB_URL is not set')
  const db = await request.post(`${stub}/_harness/db/reset`)
  if (!db.ok()) throw new Error(`database reset failed: ${db.status()}`)
  const upstream = await request.post(`${stub}/_harness/reset`)
  if (!upstream.ok()) throw new Error(`stub reset failed: ${upstream.status()}`)
}

export async function stopBackend(request: APIRequestContext): Promise<void> {
  const stub = process.env.E2E_STUB_URL
  if (!stub) throw new Error('E2E_STUB_URL is not set')
  await request.post(`${stub}/_harness/backend/stop`)
}

export async function startBackend(request: APIRequestContext): Promise<void> {
  const stub = process.env.E2E_STUB_URL
  if (!stub) throw new Error('E2E_STUB_URL is not set')
  await request.post(`${stub}/_harness/backend/start`)
}

export function trackRequests(
  page: Page,
): Array<{ method: string; url: string }> {
  const requests: Array<{ method: string; url: string }> = []
  page.on('request', (request) => {
    if (new URL(request.url()).pathname.startsWith('/api/')) {
      requests.push({ method: request.method(), url: request.url() })
    }
  })
  return requests
}

export async function dragPalette(
  page: Page,
  kind: NodeKind,
  x: number,
  y: number,
): Promise<void> {
  const palette = page.locator(`[data-testid="palette-${kind}"]`)
  const dropZone = page.locator('[data-testid="canvas-drop-zone"]')
  try {
    await palette.dragTo(dropZone, { targetPosition: { x, y } })
  } catch {
    await page.evaluate(
      ({ kind: nextKind, x: clientX, y: clientY }) => {
        const source = document.querySelector(
          `[data-testid="palette-${nextKind}"]`,
        )
        const target = document.querySelector(
          '[data-testid="canvas-drop-zone"]',
        )
        if (!source || !target)
          throw new Error('palette or drop zone is missing')
        const transfer = new DataTransfer()
        transfer.setData('application/x-devin-flow-node-kind', nextKind)
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
      { kind, x, y },
    )
  }
}

export async function connect(
  page: Page,
  sourceNodeId: string,
  targetNodeId: string,
): Promise<void> {
  const source = page.locator(
    `.vue-flow__node[data-id="${sourceNodeId}"] .vue-flow__handle-right`,
  )
  const target = page.locator(
    `.vue-flow__node[data-id="${targetNodeId}"] .vue-flow__handle-left`,
  )
  const sourceBox = await source.boundingBox()
  const targetBox = await target.boundingBox()
  if (!sourceBox || !targetBox)
    throw new Error('could not measure connection handles')
  await page.mouse.move(
    sourceBox.x + sourceBox.width / 2,
    sourceBox.y + sourceBox.height / 2,
  )
  await page.mouse.down()
  await page.mouse.move(
    targetBox.x + targetBox.width / 2,
    targetBox.y + targetBox.height / 2,
    {
      steps: 12,
    },
  )
  await page.mouse.up()
}
