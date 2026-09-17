import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '@/App.vue'

describe('App', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows API: loading before the health check resolves', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    const wrapper = mount(App)
    expect(wrapper.text()).toContain('API: loading')
  })

  it('shows API: ok when health check succeeds', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(new Response('{"status":"ok"}', { status: 200 })),
    )
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('API: ok')
  })

  it('shows API: error when health check returns a non-ok status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('oops', { status: 500 })),
    )
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('API: error')
  })

  it('shows API: error when health check fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')))
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('API: error')
  })
})
