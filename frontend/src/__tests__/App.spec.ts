import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '@/App.vue'

describe('App', () => {
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
    vi.unstubAllGlobals()
  })

  it('shows API: error when health check fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')))
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.text()).toContain('API: error')
    vi.unstubAllGlobals()
  })
})
