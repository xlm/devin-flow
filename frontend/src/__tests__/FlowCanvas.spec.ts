import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'

const fitView = vi.fn()

// VueFlow needs a real box model that jsdom cannot provide, so stub the
// component and the composable while keeping FlowCanvas' own logic intact.
vi.mock('@vue-flow/core', () => ({
  VueFlow: defineComponent({
    name: 'VueFlow',
    setup:
      (_, { slots }) =>
      () =>
        h('div', { class: 'vue-flow' }, slots.default?.()),
  }),
  useVueFlow: () => ({ fitView }),
}))
vi.mock('@vue-flow/background', () => ({
  Background: defineComponent({ render: () => h('div') }),
}))
vi.mock('@vue-flow/controls', () => ({
  Controls: defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('div', { class: 'vue-flow__controls' }, slots.default?.()),
  }),
  ControlButton: defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('button', slots.default?.()),
  }),
}))
vi.mock('@vue-flow/minimap', () => ({
  MiniMap: defineComponent({
    render: () => h('div', { class: 'vue-flow__minimap' }),
  }),
}))

const cycleMode = vi.fn()
vi.mock('@/composables/useTheme', () => ({
  useTheme: () => ({
    mode: ref('system'),
    icon: ref(defineComponent({ render: () => h('svg') })),
    cycleMode,
  }),
}))

import FlowCanvas from '@/components/FlowCanvas.vue'

function resizeWindow() {
  window.dispatchEvent(new Event('resize'))
}

describe('FlowCanvas', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    )
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    fitView.mockReset()
  })

  it('renders a viewport-sized canvas', () => {
    const wrapper = mount(FlowCanvas)
    expect(wrapper.classes()).toEqual(
      expect.arrayContaining(['h-screen', 'w-screen']),
    )
    expect(wrapper.find('.vue-flow').exists()).toBe(true)
    expect(wrapper.find('.vue-flow__minimap').exists()).toBe(true)
    wrapper.unmount()
  })

  it('cycles the theme from the controls button', async () => {
    const wrapper = mount(FlowCanvas)
    const button = wrapper.find('[data-testid="theme-toggle"]')
    expect(button.attributes('title')).toBe('Theme: system')
    await button.trigger('click')
    expect(cycleMode).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('fits the view once after a burst of window resizes', () => {
    const wrapper = mount(FlowCanvas)
    resizeWindow()
    resizeWindow()
    expect(fitView).not.toHaveBeenCalled()
    vi.runAllTimers()
    expect(fitView).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('stops listening and drops the pending fit after unmount', () => {
    const wrapper = mount(FlowCanvas)
    resizeWindow()
    wrapper.unmount()
    resizeWindow()
    vi.runAllTimers()
    expect(fitView).not.toHaveBeenCalled()
  })
})
