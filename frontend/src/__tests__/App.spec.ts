import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

vi.mock('@/components/FlowCanvas.vue', () => ({
  default: defineComponent({
    name: 'FlowCanvas',
    render: () => h('div', { 'data-testid': 'flow-canvas' }),
  }),
}))

function jsonResponse(body: string, status = 200): Response {
  return new Response(body, {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

// openapi-fetch captures globalThis.fetch and globalThis.Request when the
// client is created, so stub them before importing App (which creates the
// client). jsdom has no fetch Request and Node's rejects relative URLs, so
// stub it to accept the URL openapi-fetch builds.
async function mountApp(mock: ReturnType<typeof vi.fn>) {
  vi.resetModules()
  vi.stubGlobal(
    'Request',
    class {
      url: string
      constructor(input: string, init?: RequestInit) {
        this.url = input
        Object.assign(this, init)
      }
    },
  )
  vi.stubGlobal('fetch', mock)
  const { default: App } = await import('@/App.vue')
  return mount(App)
}

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the flow canvas with API: loading before the health check resolves', async () => {
    const wrapper = await mountApp(
      vi.fn().mockReturnValue(new Promise(() => {})),
    )
    expect(wrapper.find('[data-testid="flow-canvas"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('API: loading')
  })

  it('shows API: ok when health check succeeds', async () => {
    const wrapper = await mountApp(
      vi.fn().mockResolvedValue(jsonResponse('{"status":"ok"}')),
    )
    await flushPromises()
    expect(wrapper.text()).toContain('API: ok')
  })

  it('shows API: error when health check returns a non-ok status', async () => {
    const wrapper = await mountApp(
      vi.fn().mockResolvedValue(new Response('oops', { status: 500 })),
    )
    await flushPromises()
    expect(wrapper.text()).toContain('API: error')
  })

  it('shows API: error when health check fails', async () => {
    const wrapper = await mountApp(vi.fn().mockRejectedValue(new Error('down')))
    await flushPromises()
    expect(wrapper.text()).toContain('API: error')
  })

  it('shows API: error when health status is down', async () => {
    const wrapper = await mountApp(
      vi.fn().mockResolvedValue(jsonResponse('{"status":"down"}')),
    )
    await flushPromises()
    expect(wrapper.text()).toContain('API: error')
  })
})
