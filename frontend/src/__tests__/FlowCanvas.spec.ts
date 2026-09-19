import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import type { Edge, Node } from '@vue-flow/core'

type DragHandler = (event: { node: Node }) => void
type ChangeHandler = (changes: { type: string; id: string }[]) => void
type ConnectHandler = (connection: { source: string; target: string }) => void

const mocks = vi.hoisted(() => {
  return {
    fitView: vi.fn(),
    addNodes: vi.fn(),
    addEdges: vi.fn(),
    getEdges: { value: [] as Edge[] },
    findNode: vi.fn(),
    GET: vi.fn(),
    POST: vi.fn(),
    PATCH: vi.fn(),
    DELETE: vi.fn(),
    handlers: {} as {
      dragStart?: DragHandler
      dragStop?: DragHandler
      nodesChange?: ChangeHandler
      edgesChange?: ChangeHandler
      connect?: ConnectHandler
    },
  }
})

vi.mock('@/api/client', () => ({
  client: {
    GET: mocks.GET,
    POST: mocks.POST,
    PATCH: mocks.PATCH,
    DELETE: mocks.DELETE,
  },
}))

vi.mock('@vue-flow/core', () => ({
  VueFlow: defineComponent({
    name: 'VueFlow',
    props: {
      nodes: { type: Array, default: () => [] },
      edges: { type: Array, default: () => [] },
      isValidConnection: { type: Function, default: undefined },
    },
    setup:
      (_, { slots }) =>
      () =>
        h('div', { class: 'vue-flow' }, slots.default?.()),
  }),
  useVueFlow: () => ({
    fitView: mocks.fitView,
    findNode: mocks.findNode,
    addNodes: mocks.addNodes,
    addEdges: mocks.addEdges,
    getEdges: mocks.getEdges,
    onNodeDragStart: (handler: (event: { node: Node }) => void) => {
      mocks.handlers.dragStart = handler
    },
    onNodeDragStop: (handler: (event: { node: Node }) => void) => {
      mocks.handlers.dragStop = handler
    },
    onNodesChange: (handler: ChangeHandler) => {
      mocks.handlers.nodesChange = handler
    },
    onEdgesChange: (handler: ChangeHandler) => {
      mocks.handlers.edgesChange = handler
    },
    onConnect: (handler: ConnectHandler) => {
      mocks.handlers.connect = handler
    },
  }),
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

const canvas = {
  trigger_nodes: [{ id: 'trigger', kind: 'trigger', position: { x: 1, y: 2 } }],
  action_nodes: [{ id: 'action', kind: 'action', position: { x: 3, y: 4 } }],
  outcome_nodes: [{ id: 'outcome', kind: 'outcome', position: { x: 5, y: 6 } }],
  edges: [
    {
      id: 'edge',
      source: { id: 'trigger', kind: 'trigger' },
      target: { id: 'action', kind: 'action' },
    },
  ],
}

function response(data: unknown, error?: unknown, status?: number) {
  return {
    data,
    error,
    response: status === undefined ? undefined : { status },
  }
}

function vueFlow(wrapper: ReturnType<typeof mount>) {
  return wrapper.findComponent({ name: 'VueFlow' })
}

function resizeWindow() {
  window.dispatchEvent(new Event('resize'))
}

describe('FlowCanvas', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mocks.GET.mockResolvedValue(response(canvas))
    mocks.POST.mockResolvedValue(response(undefined))
    mocks.PATCH.mockResolvedValue(response(undefined))
    mocks.DELETE.mockResolvedValue(response(undefined))
    mocks.findNode.mockImplementation(() => undefined)
    mocks.getEdges.value.length = 0
    mocks.getEdges.value.push({
      id: 'edge',
      source: 'trigger',
      target: 'action',
      data: { sourceKind: 'trigger', targetKind: 'action' },
    })
    mocks.addEdges.mockImplementation((newEdges: Edge[]) => {
      mocks.getEdges.value.push(...newEdges)
    })
    mocks.handlers = {}
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
    vi.clearAllMocks()
  })

  it('loads nodes and edges from the API', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    expect(vueFlow(wrapper).props('nodes')).toEqual([
      {
        id: 'trigger',
        type: 'input',
        position: { x: 1, y: 2 },
        data: { kind: 'trigger', label: 'Trigger' },
      },
      {
        id: 'action',
        type: undefined,
        position: { x: 3, y: 4 },
        data: { kind: 'action', label: 'Action' },
      },
      {
        id: 'outcome',
        type: 'output',
        position: { x: 5, y: 6 },
        data: { kind: 'outcome', label: 'Outcome' },
      },
    ])
    expect(vueFlow(wrapper).props('edges')).toEqual([
      {
        id: 'edge',
        source: 'trigger',
        target: 'action',
        data: { sourceKind: 'trigger', targetKind: 'action' },
      },
    ])
    wrapper.unmount()
  })

  it('leaves an empty canvas when loading fails', async () => {
    mocks.GET.mockRejectedValue(new Error('down'))
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    expect(vueFlow(wrapper).props('nodes')).toEqual([])
    expect(vueFlow(wrapper).props('edges')).toEqual([])
    wrapper.unmount()
  })

  it('leaves an empty canvas when the response has no data', async () => {
    mocks.GET.mockResolvedValue(response(undefined))
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    expect(vueFlow(wrapper).props('nodes')).toEqual([])
    expect(vueFlow(wrapper).props('edges')).toEqual([])
    wrapper.unmount()
  })

  it('saves drag positions and reverts failed saves', async () => {
    const node = {
      id: 'trigger',
      position: { x: 1, y: 2 },
      data: { kind: 'trigger' },
    } as Node
    mocks.findNode.mockReturnValue(node)
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.handlers.dragStart?.({ node })
    node.position = { x: 8, y: 9 }
    await mocks.handlers.dragStop?.({ node })
    expect(mocks.PATCH).toHaveBeenCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      expect.objectContaining({
        params: { path: { kind: 'trigger', node_id: 'trigger' } },
        body: { position: { x: 8, y: 9 } },
      }),
    )
    mocks.PATCH.mockResolvedValue(
      response(undefined, { detail: 'save failed' }, 500),
    )
    mocks.findNode.mockReturnValue(node)
    node.position = { x: 10, y: 11 }
    await mocks.handlers.dragStop?.({ node })
    expect(node.position).toEqual({ x: 1, y: 2 })
    mocks.findNode.mockReturnValue(undefined)
    node.position = { x: 11, y: 12 }
    await mocks.handlers.dragStop?.({ node })
    expect(node.position).toEqual({ x: 11, y: 12 })
    mocks.PATCH.mockRejectedValue({ status: 500 })
    node.position = { x: 12, y: 13 }
    await mocks.handlers.dragStop?.({ node })
    expect(node.position).toEqual({ x: 12, y: 13 })
    wrapper.unmount()
  })

  it('reverts drag positions when saving throws and ignores unsaved drags', async () => {
    const node = {
      id: 'trigger',
      position: { x: 1, y: 2 },
      data: { kind: 'trigger' },
    } as Node
    mocks.findNode.mockReturnValue(node)
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.handlers.dragStop?.({ node })
    mocks.handlers.dragStart?.({ node })
    node.position = { x: 7, y: 8 }
    mocks.PATCH.mockRejectedValue(new Error('down'))
    await mocks.handlers.dragStop?.({ node })
    expect(node.position).toEqual({ x: 1, y: 2 })
    wrapper.unmount()
  })

  it('deletes nodes and restores them on non-404 failures', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.DELETE).toHaveBeenCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      { params: { path: { kind: 'trigger', node_id: 'trigger' } } },
    )
    mocks.DELETE.mockResolvedValue(
      response(undefined, { detail: 'delete failed' }, 500),
    )
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.addNodes).toHaveBeenCalledWith([
      expect.objectContaining({ id: 'trigger' }),
    ])
    wrapper.unmount()
  })

  it('treats node delete 404 and throws as expected', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.DELETE.mockResolvedValue(
      response(undefined, { detail: 'not found' }, 404),
    )
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.addNodes).not.toHaveBeenCalled()
    mocks.DELETE.mockRejectedValue({ status: 404 })
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.addNodes).toHaveBeenCalledWith([
      expect.objectContaining({ id: 'trigger' }),
    ])
    mocks.DELETE.mockRejectedValue(new Error('down'))
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.addNodes).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('ignores node removals without a snapshot or kind', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'missing' }])
    await flushPromises()
    expect(mocks.DELETE).not.toHaveBeenCalled()
    mocks.findNode.mockReturnValue({
      id: 'unknown',
      position: { x: 1, y: 2 },
      data: {},
    })
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'unknown' }])
    await flushPromises()
    expect(mocks.DELETE).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('deletes edges and restores them on non-404 failures', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.handlers.edgesChange?.([{ type: 'remove', id: 'edge' }])
    await flushPromises()
    expect(mocks.DELETE).toHaveBeenCalledWith('/api/canvas/edges/{edge_id}', {
      params: { path: { edge_id: 'edge' } },
    })
    mocks.DELETE.mockResolvedValue(
      response(undefined, { detail: 'delete failed' }, 500),
    )
    mocks.handlers.edgesChange?.([{ type: 'remove', id: 'edge' }])
    await flushPromises()
    expect(mocks.addEdges).toHaveBeenCalledWith([
      expect.objectContaining({ id: 'edge' }),
    ])
    wrapper.unmount()
  })

  it('treats edge delete 404 and missing snapshots as success', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.DELETE.mockResolvedValue(
      response(undefined, { detail: 'not found' }, 404),
    )
    mocks.handlers.edgesChange?.([{ type: 'remove', id: 'edge' }])
    await flushPromises()
    expect(mocks.addEdges).not.toHaveBeenCalled()
    mocks.handlers.edgesChange?.([{ type: 'remove', id: 'missing' }])
    await flushPromises()
    expect(mocks.DELETE).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('restores edges when deletion throws', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.DELETE.mockRejectedValue(new Error('down'))
    mocks.handlers.edgesChange?.([{ type: 'remove', id: 'edge' }])
    await flushPromises()
    expect(mocks.addEdges).toHaveBeenCalledWith([
      expect.objectContaining({ id: 'edge' }),
    ])
    mocks.DELETE.mockRejectedValue({ status: 404 })
    mocks.handlers.edgesChange?.([{ type: 'remove', id: 'edge' }])
    await flushPromises()
    expect(mocks.addEdges).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('rejects invalid connections and saves valid connections', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    const nodes = vueFlow(wrapper).props('nodes') as Node[]
    mocks.findNode.mockImplementation((id: string) =>
      nodes.find((node) => node.id === id),
    )
    mocks.handlers.connect?.({ source: 'action', target: 'trigger' })
    expect(mocks.POST).not.toHaveBeenCalled()
    mocks.POST.mockResolvedValue(
      response({
        id: 'new-edge',
        source: { id: 'action', kind: 'action' },
        target: { id: 'outcome', kind: 'outcome' },
      }),
    )
    await mocks.handlers.connect?.({ source: 'action', target: 'outcome' })
    expect(mocks.POST).toHaveBeenCalled()
    expect(mocks.addEdges).toHaveBeenCalledWith([
      expect.objectContaining({ id: 'new-edge' }),
    ])
    expect(mocks.getEdges.value).toEqual(
      expect.arrayContaining([expect.objectContaining({ id: 'new-edge' })]),
    )
    mocks.getEdges.value.length = 0
    mocks.POST.mockResolvedValue(
      response(undefined, { detail: 'connect failed' }, 500),
    )
    await mocks.handlers.connect?.({ source: 'action', target: 'outcome' })
    expect(mocks.addEdges).toHaveBeenCalledTimes(1)
    mocks.getEdges.value.length = 0
    mocks.POST.mockRejectedValue(new Error('down'))
    await mocks.handlers.connect?.({ source: 'action', target: 'outcome' })
    expect(mocks.addEdges).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('validates visual connections and ignores missing endpoints', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    const nodes = vueFlow(wrapper).props('nodes') as Node[]
    mocks.findNode.mockImplementation((id: string) =>
      nodes.find((node) => node.id === id),
    )
    const isValid = vueFlow(wrapper).props(
      'isValidConnection',
    ) as (connection: { source: string; target: string }) => boolean
    expect(isValid({ source: 'action', target: 'outcome' })).toBe(true)
    expect(isValid({ source: 'trigger', target: 'action' })).toBe(false)
    expect(isValid({ source: 'missing', target: 'action' })).toBe(false)
    mocks.handlers.connect?.({ source: 'missing', target: 'action' })
    expect(mocks.POST).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('ignores edges without source kinds during validation', async () => {
    mocks.GET.mockResolvedValue(
      response({
        ...canvas,
        edges: [
          {
            id: 'missing-kind',
            source: { id: 'trigger' },
            target: { id: 'action', kind: 'action' },
          },
        ],
      } as never),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.getEdges.value[0].data = {}
    const nodes = vueFlow(wrapper).props('nodes') as Node[]
    mocks.findNode.mockImplementation((id: string) =>
      nodes.find((node) => node.id === id),
    )
    const isValid = vueFlow(wrapper).props(
      'isValidConnection',
    ) as (connection: { source: string; target: string }) => boolean
    expect(isValid({ source: 'action', target: 'outcome' })).toBe(true)
    wrapper.unmount()
  })

  it('keeps the theme and resize behavior', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    const button = wrapper.find('[data-testid="theme-toggle"]')
    expect(button.attributes('title')).toBe('Theme: system')
    await button.trigger('click')
    expect(cycleMode).toHaveBeenCalledTimes(1)
    resizeWindow()
    resizeWindow()
    expect(mocks.fitView).not.toHaveBeenCalled()
    vi.runAllTimers()
    expect(mocks.fitView).toHaveBeenCalled()
    const fitViewCalls = mocks.fitView.mock.calls.length
    wrapper.unmount()
    resizeWindow()
    vi.runAllTimers()
    expect(mocks.fitView).toHaveBeenCalledTimes(fitViewCalls)
  })
})
