import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getContext: vi.fn(),
}))

vi.mock('@vue-flow/core', () => ({
  useVueFlow: () => ({
    dimensions: ref({ width: 100, height: 80 }),
    viewport: ref({ x: 10, y: 20, zoom: 2 }),
  }),
}))

import HelperLines from '@/components/HelperLines.vue'

function mountLines() {
  return mount(HelperLines, {
    props: { horizontal: 30, vertical: 40 },
  })
}

describe('HelperLines', () => {
  beforeEach(() => {
    mocks.getContext.mockReset()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
      mocks.getContext,
    )
  })

  it('returns early when the canvas has no context', async () => {
    mocks.getContext.mockReturnValue(null)
    const wrapper = mountLines()
    await flushPromises()
    expect(mocks.getContext).toHaveBeenCalledWith('2d')
    wrapper.unmount()
    vi.restoreAllMocks()
  })

  it('draws horizontal and vertical lines', async () => {
    const context = {
      beginPath: vi.fn(),
      clearRect: vi.fn(),
      lineTo: vi.fn(),
      moveTo: vi.fn(),
      scale: vi.fn(),
      stroke: vi.fn(),
    }
    mocks.getContext.mockReturnValue(context)
    const wrapper = mountLines()
    await flushPromises()
    expect(context.scale).toHaveBeenCalledWith(
      window.devicePixelRatio,
      window.devicePixelRatio,
    )
    expect(context.clearRect).toHaveBeenCalledWith(0, 0, 100, 80)
    expect(context.moveTo).toHaveBeenCalledWith(90, 0)
    expect(context.lineTo).toHaveBeenCalledWith(90, 80)
    expect(context.moveTo).toHaveBeenCalledWith(0, 80)
    expect(context.lineTo).toHaveBeenCalledWith(100, 80)
    expect(context.stroke).toHaveBeenCalledTimes(2)
    wrapper.unmount()
    vi.restoreAllMocks()
  })

  it('draws each line independently', async () => {
    const context = {
      beginPath: vi.fn(),
      clearRect: vi.fn(),
      lineTo: vi.fn(),
      moveTo: vi.fn(),
      scale: vi.fn(),
      stroke: vi.fn(),
    }
    mocks.getContext.mockReturnValue(context)
    const vertical = mount(HelperLines, { props: { vertical: 40 } })
    await flushPromises()
    vertical.unmount()
    const horizontal = mount(HelperLines, { props: { horizontal: 30 } })
    await flushPromises()
    horizontal.unmount()
    expect(context.stroke).toHaveBeenCalledTimes(2)
    vi.restoreAllMocks()
  })
})
