import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

vi.mock('@/components/FlowCanvas.vue', () => ({
  default: defineComponent({
    name: 'FlowCanvas',
    render: () => h('div', { 'data-testid': 'flow-canvas' }),
  }),
}))

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function healthBody(polling: Record<string, unknown> = {}) {
  return {
    status: 'ok',
    polling: {
      enabled: true,
      interval_seconds: 60,
      last_success_at: '2026-01-01T12:00:00Z',
      stale: false,
      ...polling,
    },
  }
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
  const { HEALTH_POLL_INTERVAL_MS } = await import('@/composables/useApiHealth')
  return { wrapper: mount(App), interval: HEALTH_POLL_INTERVAL_MS }
}

function indicator(wrapper: ReturnType<typeof mount>) {
  return wrapper.find('[data-testid="api-status"]')
}

describe('App', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('renders the flow canvas and a connecting indicator before the health check resolves', async () => {
    const { wrapper } = await mountApp(
      vi.fn().mockReturnValue(new Promise(() => {})),
    )
    expect(wrapper.find('[data-testid="flow-canvas"]').exists()).toBe(true)
    const status = indicator(wrapper)
    expect(status.attributes('data-tone')).toBe('loading')
    expect(status.classes()).toContain('pointer-events-none')
  })

  it('shows green Live when the API is ok and the poller is fresh', async () => {
    const { wrapper } = await mountApp(
      vi.fn().mockResolvedValue(jsonResponse(healthBody())),
    )
    await flushPromises()
    const status = indicator(wrapper)
    expect(status.attributes('data-tone')).toBe('green')
    expect(status.text()).toBe('Live')
    expect(status.attributes('title')).toContain('every 60s')
  })

  it('shows amber Polling stale when the poller is stale', async () => {
    const { wrapper } = await mountApp(
      vi.fn().mockResolvedValue(jsonResponse(healthBody({ stale: true }))),
    )
    await flushPromises()
    const status = indicator(wrapper)
    expect(status.attributes('data-tone')).toBe('amber')
    expect(status.text()).toBe('Polling stale')
  })

  it('shows amber Polling off when polling is disabled', async () => {
    const { wrapper } = await mountApp(
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            healthBody({ enabled: false, interval_seconds: 0, stale: false }),
          ),
        ),
    )
    await flushPromises()
    const status = indicator(wrapper)
    expect(status.attributes('data-tone')).toBe('amber')
    expect(status.text()).toBe('Polling off')
  })

  it('shows red API error when the health request fails', async () => {
    const { wrapper } = await mountApp(
      vi.fn().mockResolvedValue(new Response('oops', { status: 500 })),
    )
    await flushPromises()
    const status = indicator(wrapper)
    expect(status.attributes('data-tone')).toBe('red')
    expect(status.text()).toBe('API error')
  })

  it('flips from API error back to Live on the next poll without a reload', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValue(jsonResponse(healthBody()))
    const { wrapper, interval } = await mountApp(fetchMock)
    await flushPromises()
    expect(indicator(wrapper).attributes('data-tone')).toBe('red')
    await vi.advanceTimersByTimeAsync(interval)
    expect(indicator(wrapper).attributes('data-tone')).toBe('green')
    expect(indicator(wrapper).text()).toBe('Live')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
