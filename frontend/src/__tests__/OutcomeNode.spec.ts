import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { REFRESH_SYNC_STATE } from '@/lib/canvasInjection'

const mocks = vi.hoisted(() => ({
  PATCH: vi.fn(),
  removeNodes: vi.fn(),
  updateNodeData: vi.fn(),
  refreshSyncState: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  client: { PATCH: mocks.PATCH },
}))

vi.mock('@vue-flow/core', () => ({
  Handle: defineComponent({
    props: { type: String, position: String },
    setup(props) {
      return () => h('span', { class: 'handle', 'data-type': props.type })
    },
  }),
  Position: { Left: 'left', Right: 'right', Top: 'top' },
  useVueFlow: () => ({
    removeNodes: mocks.removeNodes,
    updateNodeData: mocks.updateNodeData,
  }),
}))

vi.mock('@vue-flow/node-toolbar', () => ({
  NodeToolbar: defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.()),
  }),
}))

import OutcomeNode from '@/components/nodes/OutcomeNode.vue'
import type { OutcomeRead } from '@/lib/connectRules'

function savedResponse(outcome: OutcomeRead) {
  return {
    data: {
      id: 'node-1',
      kind: 'outcome',
      position: { x: 1, y: 2 },
      outcome,
    },
    error: undefined,
  }
}

function mountNode(outcome?: OutcomeRead) {
  return mount(OutcomeNode, {
    props: {
      id: 'node-1',
      data: { kind: 'outcome', label: 'Outcome', outcome },
    } as never,
    global: {
      provide: {
        [REFRESH_SYNC_STATE as symbol]: mocks.refreshSyncState,
      },
    },
  })
}

describe('OutcomeNode', () => {
  beforeEach(() => {
    mocks.PATCH.mockReset()
    mocks.removeNodes.mockReset()
    mocks.updateNodeData.mockReset()
    mocks.refreshSyncState.mockReset()
    mocks.PATCH.mockResolvedValue(savedResponse({ kind: 'duplicate' }))
  })

  it('renders the kind select and starts incomplete', async () => {
    const wrapper = mountNode()
    await flushPromises()
    const select = wrapper.find('[data-testid="outcome-kind"]')
    expect(select.exists()).toBe(true)
    expect(select.findAll('option').map((option) => option.text())).toEqual([
      'Select kind',
      'Pull Request',
      'Duplicate',
      'Not reproducible',
      'Not a bug',
    ])
    expect(
      wrapper.find('[data-testid="canvas-node"]').attributes('data-incomplete'),
    ).toBe('true')
    wrapper.unmount()
  })

  it('renders complete when a kind is set', async () => {
    const wrapper = mountNode({ kind: 'not_a_bug' })
    await flushPromises()
    expect(
      wrapper.find('[data-testid="canvas-node"]').attributes('data-incomplete'),
    ).toBe('false')
    expect(
      (
        wrapper.find('[data-testid="outcome-kind"]')
          .element as HTMLSelectElement
      ).value,
    ).toBe('not_a_bug')
    wrapper.unmount()
  })

  it('saves a selected kind and refreshes sync state', async () => {
    const wrapper = mountNode()
    await flushPromises()
    await wrapper.find('[data-testid="outcome-kind"]').setValue('duplicate')
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      {
        params: { path: { kind: 'outcome', node_id: 'node-1' } },
        body: { outcome: { kind: 'duplicate' } },
      },
    )
    expect(mocks.updateNodeData).toHaveBeenCalledWith('node-1', {
      outcome: { kind: 'duplicate' },
    })
    expect(mocks.refreshSyncState).toHaveBeenCalled()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('saves null when the kind is cleared', async () => {
    mocks.PATCH.mockResolvedValue(savedResponse({ kind: null }))
    const wrapper = mountNode({ kind: 'duplicate' })
    await flushPromises()
    await wrapper.find('[data-testid="outcome-kind"]').setValue('')
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      expect.objectContaining({ body: { outcome: { kind: null } } }),
    )
    wrapper.unmount()
  })

  it('reverts to an empty selection when a first save fails', async () => {
    mocks.PATCH.mockRejectedValueOnce(new Error('down'))
    const wrapper = mountNode()
    await flushPromises()
    const select = wrapper.find('[data-testid="outcome-kind"]')
    await select.setValue('duplicate')
    await flushPromises()
    expect((select.element as HTMLSelectElement).value).toBe('')
    expect(wrapper.find('[role="alert"]').text()).toBe('Could not save')
    wrapper.unmount()
  })

  it('saves without an injected refresh callback', async () => {
    const wrapper = mount(OutcomeNode, {
      props: {
        id: 'node-1',
        data: { kind: 'outcome', label: 'Outcome' },
      } as never,
    })
    await flushPromises()
    await wrapper.find('[data-testid="outcome-kind"]').setValue('duplicate')
    await flushPromises()
    expect(mocks.updateNodeData).toHaveBeenCalledWith('node-1', {
      outcome: { kind: 'duplicate' },
    })
    wrapper.unmount()
  })

  it.each([false, true])(
    'reverts the select and reports save failures (%s)',
    async (throws) => {
      mocks.PATCH.mockImplementationOnce(() =>
        throws
          ? Promise.reject(new Error('down'))
          : Promise.resolve({ error: { detail: 'failed' } }),
      )
      const wrapper = mountNode({ kind: 'duplicate' })
      await flushPromises()
      const select = wrapper.find('[data-testid="outcome-kind"]')
      await select.setValue('not_a_bug')
      await flushPromises()
      expect((select.element as HTMLSelectElement).value).toBe('duplicate')
      expect(wrapper.find('[role="alert"]').text()).toBe('Could not save')
      wrapper.unmount()
    },
  )
})
