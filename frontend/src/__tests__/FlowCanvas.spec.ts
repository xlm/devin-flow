import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, inject, ref } from 'vue'
import type { Edge, Node } from '@vue-flow/core'
import { NODE_KIND_MIME } from '@/lib/nodeKinds'
import { SAVE_NODE_FIELDS, type SaveNodeFields } from '@/lib/canvasInjection'

type DragHandler = (event: { node: Node }) => void | Promise<void>
type ChangeHandler = (changes: { type: string; id: string }[]) => void
type ConnectHandler = (connection: { source: string; target: string }) => void
type EdgeClickHandler = (event: {
  edge: {
    source: string
    target: string
    data?: Record<string, unknown>
  }
}) => void

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
    screenToFlowCoordinate: vi.fn(),
    removeNodes: vi.fn(),
    handlers: {} as {
      dragStop?: DragHandler
      nodesChange?: ChangeHandler
      edgesChange?: ChangeHandler
      connect?: ConnectHandler
      edgeClick?: EdgeClickHandler
    },
    sheetProps: {} as Record<string, unknown>,
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
      nodeTypes: { type: Object, default: () => ({}) },
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
    screenToFlowCoordinate: mocks.screenToFlowCoordinate,
    removeNodes: mocks.removeNodes,
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
    onEdgeClick: (handler: EdgeClickHandler) => {
      mocks.handlers.edgeClick = handler
    },
  }),
}))

vi.mock('@/components/OutcomeInvocationsSheet.vue', () => ({
  default: defineComponent({
    name: 'OutcomeInvocationsSheet',
    props: {
      open: { type: Boolean, default: false },
      nodeId: { type: String, default: null },
      actionNodeId: { type: String, default: null },
      kind: { type: String, default: null },
    },
    emits: ['update:open'],
    setup(props) {
      mocks.sheetProps = props
      return () => h('div', { 'data-testid': 'outcome-sheet-stub' })
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
  trigger_nodes: [
    {
      id: 'trigger',
      kind: 'trigger',
      position: { x: 1, y: 2 },
      trigger: { event_action: null, repository_full_name: null },
    },
  ],
  action_nodes: [
    {
      id: 'action',
      kind: 'action',
      position: { x: 3, y: 4 },
      name: '',
      playbook_id: null,
      prompt: '',
      enabled: false,
      sync_status: 'unprovisioned',
      sync_error: null,
      automation_id: null,
      invocation_count: 2,
    },
  ],
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

function saveProbe(provided: { value: SaveNodeFields | undefined }) {
  return defineComponent({
    setup: () => {
      provided.value = inject(SAVE_NODE_FIELDS)
      return () => h('div')
    },
  })
}

describe('FlowCanvas', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mocks.GET.mockResolvedValue(response(canvas))
    mocks.POST.mockResolvedValue(response(undefined))
    mocks.PATCH.mockResolvedValue(response(undefined))
    mocks.DELETE.mockResolvedValue(response(undefined))
    mocks.screenToFlowCoordinate.mockReturnValue({ x: 0, y: 0 })
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
        type: 'trigger',
        position: { x: 1, y: 2 },
        data: {
          kind: 'trigger',
          label: 'Trigger',
          trigger: { event_action: null, repository_full_name: null },
        },
      },
      {
        id: 'action',
        type: 'action',
        position: { x: 3, y: 4 },
        data: {
          kind: 'action',
          label: 'Action',
          name: '',
          playbookId: null,
          prompt: '',
          enabled: false,
          syncStatus: 'unprovisioned',
          syncError: null,
          invocationCount: 2,
        },
      },
      {
        id: 'outcome',
        type: 'outcome',
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
        label: '2 invocations',
      },
    ])
    expect(wrapper.find('[data-testid="load-error"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('creates a node from a palette drop and stores its snapshot', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.screenToFlowCoordinate.mockReturnValue({ x: 40, y: 50 })
    mocks.POST.mockResolvedValue(
      response({
        id: 'new',
        kind: 'action',
        position: { x: 40, y: 50 },
        name: '',
        playbook_id: null,
        prompt: '',
        enabled: false,
        sync_status: 'unprovisioned',
        sync_error: null,
      }),
    )
    const dataTransfer = {
      types: [NODE_KIND_MIME],
      getData: vi.fn().mockReturnValue('action'),
      dropEffect: '',
    }
    const event = new Event('drop', { bubbles: true, cancelable: true })
    Object.defineProperty(event, 'dataTransfer', { value: dataTransfer })
    Object.defineProperty(event, 'clientX', { value: 100 })
    Object.defineProperty(event, 'clientY', { value: 200 })
    wrapper
      .find('[data-testid="canvas-drop-zone"]')
      .element.dispatchEvent(event)
    await flushPromises()
    expect(mocks.POST).toHaveBeenCalledWith('/api/canvas/nodes/{kind}', {
      params: { path: { kind: 'action' } },
      body: { position: { x: 40, y: 50 } },
    })
    expect(mocks.addNodes).toHaveBeenCalledWith([
      expect.objectContaining({ id: 'new', type: 'action' }),
    ])
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'new' }])
    await flushPromises()
    expect(mocks.DELETE).toHaveBeenCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      { params: { path: { kind: 'action', node_id: 'new' } } },
    )
    wrapper.unmount()
  })

  it('blocks palette drops while the canvas is loading', async () => {
    let resolveLoad: ((value: ReturnType<typeof response>) => void) | undefined
    mocks.GET.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveLoad = resolve
        }),
    )
    const wrapper = mount(FlowCanvas)
    const dropZone = wrapper.find('[data-testid="canvas-drop-zone"]')
    const dataTransfer = {
      types: [NODE_KIND_MIME],
      getData: vi.fn().mockReturnValue('action'),
      dropEffect: '',
    }
    const dragOverEvent = new Event('dragover', {
      bubbles: true,
      cancelable: true,
    })
    Object.defineProperty(dragOverEvent, 'dataTransfer', {
      value: dataTransfer,
    })
    dropZone.element.dispatchEvent(dragOverEvent)
    expect(dragOverEvent.defaultPrevented).toBe(false)
    const dropEvent = new Event('drop', {
      bubbles: true,
      cancelable: true,
    })
    Object.defineProperty(dropEvent, 'dataTransfer', { value: dataTransfer })
    Object.defineProperty(dropEvent, 'clientX', { value: 100 })
    Object.defineProperty(dropEvent, 'clientY', { value: 200 })
    dropZone.element.dispatchEvent(dropEvent)
    await flushPromises()
    expect(mocks.POST).not.toHaveBeenCalled()
    expect(
      wrapper.find('[data-testid="palette-action"]').attributes('draggable'),
    ).toBe('false')
    resolveLoad?.(response(canvas))
    await flushPromises()
    expect(
      wrapper.find('[data-testid="palette-action"]').attributes('draggable'),
    ).toBe('true')
    mocks.POST.mockResolvedValue(
      response({
        id: 'new',
        kind: 'action',
        position: { x: 0, y: 0 },
        name: '',
        playbook_id: null,
        prompt: '',
        enabled: false,
        sync_status: 'unprovisioned',
        sync_error: null,
      }),
    )
    const secondDrop = new Event('drop', {
      bubbles: true,
      cancelable: true,
    })
    Object.defineProperty(secondDrop, 'dataTransfer', { value: dataTransfer })
    Object.defineProperty(secondDrop, 'clientX', { value: 100 })
    Object.defineProperty(secondDrop, 'clientY', { value: 200 })
    dropZone.element.dispatchEvent(secondDrop)
    await flushPromises()
    expect(mocks.POST).toHaveBeenCalledWith(
      '/api/canvas/nodes/{kind}',
      expect.objectContaining({ params: { path: { kind: 'action' } } }),
    )
    wrapper.unmount()
  })

  it('accepts only node palette drag events', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    const dropZone = wrapper.find('[data-testid="canvas-drop-zone"]')
    const dataTransfer = {
      types: [NODE_KIND_MIME],
      getData: vi.fn().mockReturnValue('action'),
      dropEffect: '',
    }
    const dragOverEvent = new Event('dragover', {
      bubbles: true,
      cancelable: true,
    })
    Object.defineProperty(dragOverEvent, 'dataTransfer', {
      value: dataTransfer,
    })
    dropZone.element.dispatchEvent(dragOverEvent)
    expect(dragOverEvent.defaultPrevented).toBe(true)
    expect(dataTransfer.dropEffect).toBe('move')
    const unrelatedTransfer = {
      types: ['text/plain'],
      getData: vi.fn().mockReturnValue('action'),
      dropEffect: '',
    }
    const unrelatedDragOver = new Event('dragover', {
      bubbles: true,
      cancelable: true,
    })
    Object.defineProperty(unrelatedDragOver, 'dataTransfer', {
      value: unrelatedTransfer,
    })
    dropZone.element.dispatchEvent(unrelatedDragOver)
    expect(unrelatedDragOver.defaultPrevented).toBe(false)
    const unrelatedDrop = new Event('drop', {
      bubbles: true,
      cancelable: true,
    })
    Object.defineProperty(unrelatedDrop, 'dataTransfer', {
      value: unrelatedTransfer,
    })
    dropZone.element.dispatchEvent(unrelatedDrop)
    await flushPromises()
    expect(mocks.POST).not.toHaveBeenCalled()
    const invalidTransfer = {
      types: [NODE_KIND_MIME],
      getData: vi.fn().mockReturnValue('bogus'),
      dropEffect: '',
    }
    const invalidDrop = new Event('drop', {
      bubbles: true,
      cancelable: true,
    })
    Object.defineProperty(invalidDrop, 'dataTransfer', {
      value: invalidTransfer,
    })
    dropZone.element.dispatchEvent(invalidDrop)
    await flushPromises()
    expect(mocks.POST).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('does not add nodes when node creation fails', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    const dataTransfer = {
      types: [NODE_KIND_MIME],
      getData: vi.fn().mockReturnValue('action'),
      dropEffect: '',
    }
    const dispatchDrop = () => {
      const event = new Event('drop', { bubbles: true, cancelable: true })
      Object.defineProperty(event, 'dataTransfer', { value: dataTransfer })
      Object.defineProperty(event, 'clientX', { value: 100 })
      Object.defineProperty(event, 'clientY', { value: 200 })
      wrapper
        .find('[data-testid="canvas-drop-zone"]')
        .element.dispatchEvent(event)
    }
    mocks.POST.mockResolvedValue(response(undefined, { detail: 'failed' }, 500))
    dispatchDrop()
    await flushPromises()
    expect(mocks.addNodes).not.toHaveBeenCalled()
    mocks.POST.mockRejectedValue(new Error('down'))
    dispatchDrop()
    await flushPromises()
    expect(mocks.addNodes).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('leaves an empty canvas when loading fails', async () => {
    mocks.GET.mockRejectedValue(new Error('down'))
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    expect(vueFlow(wrapper).props('nodes')).toEqual([])
    expect(vueFlow(wrapper).props('edges')).toEqual([])
    expect(wrapper.find('[data-testid="load-error"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('blocks palette drops after a failed load until retry succeeds', async () => {
    mocks.GET.mockRejectedValueOnce(new Error('down'))
    mocks.GET.mockResolvedValueOnce(response(canvas))
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    const dropZone = wrapper.find('[data-testid="canvas-drop-zone"]')
    const dataTransfer = {
      types: [NODE_KIND_MIME],
      getData: vi.fn().mockReturnValue('action'),
      dropEffect: '',
    }
    const dispatchDrop = () => {
      const event = new Event('drop', { bubbles: true, cancelable: true })
      Object.defineProperty(event, 'dataTransfer', { value: dataTransfer })
      Object.defineProperty(event, 'clientX', { value: 100 })
      Object.defineProperty(event, 'clientY', { value: 200 })
      dropZone.element.dispatchEvent(event)
    }
    dispatchDrop()
    await flushPromises()
    expect(mocks.POST).not.toHaveBeenCalled()
    expect(
      wrapper.find('[data-testid="palette-action"]').attributes('draggable'),
    ).toBe('false')
    await wrapper.find('[data-testid="load-retry"]').trigger('click')
    await flushPromises()
    expect(
      wrapper.find('[data-testid="palette-action"]').attributes('draggable'),
    ).toBe('true')
    mocks.POST.mockResolvedValue(
      response({
        id: 'new',
        kind: 'action',
        position: { x: 0, y: 0 },
        name: '',
        playbook_id: null,
        prompt: '',
        enabled: false,
        sync_status: 'unprovisioned',
        sync_error: null,
      }),
    )
    dispatchDrop()
    await flushPromises()
    expect(mocks.POST).toHaveBeenCalledWith(
      '/api/canvas/nodes/{kind}',
      expect.objectContaining({ params: { path: { kind: 'action' } } }),
    )
    wrapper.unmount()
  })

  it('leaves an empty canvas when the response has no data', async () => {
    mocks.GET.mockResolvedValue(response(undefined))
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    expect(vueFlow(wrapper).props('nodes')).toEqual([])
    expect(vueFlow(wrapper).props('edges')).toEqual([])
    expect(wrapper.find('[data-testid="load-error"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows a load error when the API returns an error', async () => {
    mocks.GET.mockResolvedValue(response(undefined, { detail: 'down' }))
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    expect(wrapper.find('[data-testid="load-error"]').exists()).toBe(true)
    expect(vueFlow(wrapper).props('nodes')).toEqual([])
    wrapper.unmount()
  })

  it('retries loading the canvas', async () => {
    mocks.GET.mockRejectedValueOnce(new Error('down'))
    mocks.GET.mockResolvedValueOnce(response(canvas))
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    expect(wrapper.find('[data-testid="load-error"]').exists()).toBe(true)
    await wrapper.find('[data-testid="load-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="load-error"]').exists()).toBe(false)
    expect(vueFlow(wrapper).props('nodes')).toHaveLength(3)
    wrapper.unmount()
  })

  it('shares an in-flight load across duplicate retries', async () => {
    let resolveRetry: ((value: ReturnType<typeof response>) => void) | undefined
    mocks.GET.mockRejectedValueOnce(new Error('down')).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveRetry = resolve
        }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    const retry = wrapper.find('[data-testid="load-retry"]')
    await retry.trigger('click')
    await retry.trigger('click')
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    resolveRetry?.(response(canvas))
    await flushPromises()
    expect(vueFlow(wrapper).props('nodes')).toHaveLength(3)
    expect(wrapper.find('[data-testid="load-error"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('clears snapshots when retrying a different canvas', async () => {
    mocks.GET.mockResolvedValueOnce(response(canvas))
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValueOnce(
        response({
          trigger_nodes: [],
          action_nodes: [
            {
              id: 'replacement',
              kind: 'action',
              position: { x: 7, y: 8 },
              name: '',
              playbook_id: null,
              prompt: '',
              enabled: false,
              sync_status: 'unprovisioned',
              sync_error: null,
            },
          ],
          outcome_nodes: [],
          edges: [],
        }),
      )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    await (
      wrapper.vm as unknown as {
        loadCanvas: () => Promise<void>
      }
    ).loadCanvas()
    await flushPromises()
    await wrapper.find('[data-testid="load-retry"]').trigger('click')
    await flushPromises()
    mocks.DELETE.mockResolvedValue(
      response(undefined, { detail: 'delete failed' }, 500),
    )
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'replacement' }])
    await flushPromises()
    expect(mocks.addEdges).not.toHaveBeenCalled()
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
    expect(node.position).toEqual({ x: 8, y: 9 })
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
    node.position = { x: 7, y: 8 }
    mocks.PATCH.mockRejectedValue(new Error('down'))
    await mocks.handlers.dragStop?.({ node })
    expect(node.position).toEqual({ x: 1, y: 2 })
    wrapper.unmount()
  })

  it('leaves failed drags without persisted nodes unchanged', async () => {
    const unknown = {
      id: 'unknown',
      position: { x: 1, y: 2 },
      data: { kind: 'trigger' },
    } as Node
    mocks.PATCH.mockResolvedValue(
      response(undefined, { detail: 'save failed' }, 500),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    await mocks.handlers.dragStop?.({ node: unknown })
    expect(unknown.position).toEqual({ x: 1, y: 2 })
    mocks.PATCH.mockRejectedValue(new Error('down'))
    unknown.position = { x: 3, y: 4 }
    await mocks.handlers.dragStop?.({ node: unknown })
    expect(unknown.position).toEqual({ x: 3, y: 4 })
    mocks.PATCH.mockResolvedValue(response(undefined))
    unknown.position = { x: 4, y: 5 }
    await mocks.handlers.dragStop?.({ node: unknown })
    expect(unknown.position).toEqual({ x: 4, y: 5 })
    const missingKind = {
      id: 'missing-kind',
      position: { x: 5, y: 6 },
      data: {},
    } as Node
    await mocks.handlers.dragStop?.({ node: missingKind })
    expect(missingKind.position).toEqual({ x: 5, y: 6 })
    wrapper.unmount()
  })

  it('serializes drag saves and updates persisted positions', async () => {
    const node = {
      id: 'trigger',
      position: { x: 1, y: 2 },
      data: { kind: 'trigger' },
    } as Node
    mocks.findNode.mockReturnValue(node)
    let resolveFirst: ((value: ReturnType<typeof response>) => void) | undefined
    let resolveSecond:
      ((value: ReturnType<typeof response>) => void) | undefined
    mocks.PATCH.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve
        }),
    ).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSecond = resolve
        }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    node.position = { x: 8, y: 9 }
    const firstSave = mocks.handlers.dragStop?.({ node })
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledTimes(1)
    node.position = { x: 10, y: 11 }
    const secondSave = mocks.handlers.dragStop?.({ node })
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledTimes(1)
    resolveFirst?.(response(undefined))
    await firstSave
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledTimes(2)
    expect(mocks.PATCH.mock.calls[0][1]).toEqual(
      expect.objectContaining({ body: { position: { x: 8, y: 9 } } }),
    )
    expect(mocks.PATCH.mock.calls[1][1]).toEqual(
      expect.objectContaining({ body: { position: { x: 10, y: 11 } } }),
    )
    resolveSecond?.(response(undefined, { detail: 'save failed' }, 500))
    await secondSave
    expect(node.position).toEqual({ x: 8, y: 9 })
    wrapper.unmount()
  })

  it('ignores stale drag save failures', async () => {
    const node = {
      id: 'trigger',
      position: { x: 1, y: 2 },
      data: { kind: 'trigger' },
    } as Node
    mocks.findNode.mockReturnValue(node)
    let rejectFirst: ((reason?: unknown) => void) | undefined
    let resolveSecond:
      ((value: ReturnType<typeof response>) => void) | undefined
    mocks.PATCH.mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          rejectFirst = reject
        }),
    ).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSecond = resolve
        }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    node.position = { x: 8, y: 9 }
    const firstSave = mocks.handlers.dragStop?.({ node })
    await flushPromises()
    node.position = { x: 10, y: 11 }
    const secondSave = mocks.handlers.dragStop?.({ node })
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledTimes(1)
    rejectFirst?.(new Error('down'))
    await firstSave
    await flushPromises()
    resolveSecond?.(response(undefined))
    await secondSave
    expect(node.position).toEqual({ x: 10, y: 11 })
    wrapper.unmount()
  })

  it('rolls back queued failed drags to the persisted position', async () => {
    const node = {
      id: 'trigger',
      position: { x: 1, y: 2 },
      data: { kind: 'trigger' },
    } as Node
    mocks.findNode.mockReturnValue(node)
    let resolveFirst: ((value: ReturnType<typeof response>) => void) | undefined
    let resolveSecond:
      ((value: ReturnType<typeof response>) => void) | undefined
    mocks.PATCH.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve
        }),
    ).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSecond = resolve
        }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    node.position = { x: 8, y: 9 }
    const firstSave = mocks.handlers.dragStop?.({ node })
    await flushPromises()
    node.position = { x: 10, y: 11 }
    const secondSave = mocks.handlers.dragStop?.({ node })
    await flushPromises()
    resolveFirst?.(response(undefined, { detail: 'save failed' }, 500))
    await firstSave
    await flushPromises()
    resolveSecond?.(response(undefined, { detail: 'save failed' }, 500))
    await secondSave
    expect(node.position).toEqual({ x: 1, y: 2 })
    wrapper.unmount()
  })

  it('continues drag saves after a rejected save chain', async () => {
    const node = {
      id: 'trigger',
      position: { x: 1, y: 2 },
      data: { kind: 'trigger' },
    } as Node
    mocks.findNode.mockImplementation(() => {
      throw new Error('down')
    })
    mocks.PATCH.mockResolvedValue(
      response(undefined, { detail: 'save failed' }, 500),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    node.position = { x: 8, y: 9 }
    const firstSave = mocks.handlers.dragStop?.({ node })
    if (firstSave) await firstSave.catch(() => {})
    mocks.findNode.mockReturnValue(node)
    node.position = { x: 10, y: 11 }
    await mocks.handlers.dragStop?.({ node })
    expect(mocks.PATCH).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('saves action fields optimistically and updates its snapshot', async () => {
    const node = {
      id: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: '',
        playbookId: null,
        prompt: '',
      },
    } as Node
    const provided = { value: undefined as SaveNodeFields | undefined }
    mocks.findNode.mockReturnValue(node)
    const wrapper = mount(FlowCanvas, {
      global: { stubs: { NodePalette: saveProbe(provided) } },
    })
    await flushPromises()
    expect(await provided.value?.('action', { name: 'Triage' })).toBe(true)
    expect(node.data.name).toBe('Triage')
    expect(mocks.PATCH).toHaveBeenLastCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      {
        params: { path: { kind: 'action', node_id: 'action' } },
        body: { name: 'Triage' },
      },
    )
    mocks.PATCH.mockResolvedValue(
      response(undefined, { detail: 'failed' }, 500),
    )
    expect(await provided.value?.('action', { playbookId: 'pb-1' })).toBe(false)
    expect(node.data).toEqual({
      kind: 'action',
      name: 'Triage',
      playbookId: null,
      prompt: '',
    })
    wrapper.unmount()
  })

  it('applies synchronization data from an action save response', async () => {
    const node = {
      id: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: 'Triage',
        playbookId: 'pb-1',
        prompt: '',
        enabled: false,
      },
    } as Node
    const provided = { value: undefined as SaveNodeFields | undefined }
    mocks.findNode.mockReturnValue(node)
    mocks.PATCH.mockResolvedValue(
      response({
        id: 'action',
        kind: 'action',
        position: { x: 3, y: 4 },
        name: 'Triage',
        playbook_id: 'pb-1',
        prompt: '',
        enabled: true,
        sync_status: 'enabled',
        sync_error: null,
        automation_id: 'auto-1',
      }),
    )
    const wrapper = mount(FlowCanvas, {
      global: { stubs: { NodePalette: saveProbe(provided) } },
    })
    await flushPromises()
    mocks.findNode.mockReturnValue(node)
    expect(await provided.value?.('action', { enabled: true })).toBe(true)
    expect(node.data).toEqual({
      kind: 'action',
      label: 'Action',
      name: '',
      playbookId: null,
      prompt: '',
      enabled: true,
      syncStatus: 'enabled',
      syncError: null,
      invocationCount: 2,
    })
    expect(mocks.PATCH).toHaveBeenLastCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      expect.objectContaining({ body: { enabled: true } }),
    )
    mocks.PATCH.mockResolvedValue(
      response({
        id: 'action',
        kind: 'action',
        position: { x: 3, y: 4 },
        name: 'Triage',
        playbook_id: 'pb-1',
        prompt: '',
        enabled: false,
        sync_status: 'disabled',
        sync_error: null,
        automation_id: 'auto-1',
      }),
    )
    mocks.findNode.mockReturnValueOnce(node).mockReturnValueOnce(undefined)
    expect(await provided.value?.('action', { enabled: false })).toBe(true)
    vi.runAllTimers()
    wrapper.unmount()
  })

  it('rolls back action fields when saving throws', async () => {
    const node = {
      id: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: '',
        playbookId: null,
        prompt: '',
      },
    } as Node
    const provided = { value: undefined as SaveNodeFields | undefined }
    mocks.findNode.mockReturnValue(node)
    mocks.PATCH.mockRejectedValue(new Error('down'))
    const wrapper = mount(FlowCanvas, {
      global: { stubs: { NodePalette: saveProbe(provided) } },
    })
    await flushPromises()
    await provided.value?.('action', { prompt: 'Notes' })
    expect(node.data.prompt).toBe('')
    wrapper.unmount()
  })

  it('keeps newer queued name edits when an earlier save fails', async () => {
    const node = {
      id: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: '',
        playbookId: null,
        prompt: '',
      },
    } as Node
    const provided = { value: undefined as SaveNodeFields | undefined }
    mocks.findNode.mockReturnValue(node)
    let rejectFirst: ((reason?: unknown) => void) | undefined
    mocks.PATCH.mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          rejectFirst = reject
        }),
    ).mockResolvedValueOnce(response(undefined))
    const wrapper = mount(FlowCanvas, {
      global: { stubs: { NodePalette: saveProbe(provided) } },
    })
    await flushPromises()
    const first = provided.value?.('action', { name: 'First' })
    await flushPromises()
    const second = provided.value?.('action', { name: 'Second' })
    rejectFirst?.(new Error('down'))
    await first
    expect(node.data.name).toBe('Second')
    await second
    expect(node.data.name).toBe('Second')
    mocks.PATCH.mockResolvedValue(
      response(undefined, { detail: 'failed' }, 500),
    )
    await provided.value?.('action', { name: 'Third' })
    expect(node.data.name).toBe('Second')
    wrapper.unmount()
  })

  it('reverts failed fields while keeping later field saves', async () => {
    const node = {
      id: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: '',
        playbookId: null,
        prompt: '',
      },
    } as Node
    const provided = { value: undefined as SaveNodeFields | undefined }
    mocks.findNode.mockReturnValue(node)
    let rejectFirst: ((reason?: unknown) => void) | undefined
    let resolveSecond:
      ((value: ReturnType<typeof response>) => void) | undefined
    mocks.PATCH.mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          rejectFirst = reject
        }),
    ).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSecond = resolve
        }),
    )
    const wrapper = mount(FlowCanvas, {
      global: { stubs: { NodePalette: saveProbe(provided) } },
    })
    await flushPromises()
    const first = provided.value?.('action', { name: 'First' })
    await flushPromises()
    const second = provided.value?.('action', { playbookId: 'pb-1' })
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledTimes(1)
    rejectFirst?.(new Error('down'))
    await first
    await flushPromises()
    expect(node.data).toEqual({
      kind: 'action',
      name: '',
      playbookId: 'pb-1',
      prompt: '',
    })
    resolveSecond?.(response(undefined))
    await second
    mocks.PATCH.mockResolvedValue(
      response(undefined, { detail: 'failed' }, 500),
    )
    await provided.value?.('action', { name: 'Third' })
    expect(node.data).toEqual({
      kind: 'action',
      name: '',
      playbookId: 'pb-1',
      prompt: '',
    })
    wrapper.unmount()
  })

  it('keeps field snapshots separate from optimistic position saves', async () => {
    const node = {
      id: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: '',
        playbookId: null,
        prompt: '',
      },
    } as Node
    const provided = { value: undefined as SaveNodeFields | undefined }
    mocks.findNode.mockReturnValue(node)
    let rejectField: ((value: ReturnType<typeof response>) => void) | undefined
    let resolvePosition:
      ((value: ReturnType<typeof response>) => void) | undefined
    mocks.PATCH.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          rejectField = resolve
        }),
    ).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolvePosition = resolve
        }),
    )
    const wrapper = mount(FlowCanvas, {
      global: { stubs: { NodePalette: saveProbe(provided) } },
    })
    await flushPromises()
    const fieldSave = provided.value?.('action', { name: 'Edited' })
    await flushPromises()
    node.position = { x: 10, y: 11 }
    const positionSave = mocks.handlers.dragStop?.({ node })
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledTimes(1)
    rejectField?.(response(undefined, { detail: 'failed' }, 500))
    await fieldSave
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledTimes(2)
    resolvePosition?.(response(undefined))
    await positionSave
    expect(node.data.name).toBe('')
    expect(node.position).toEqual({ x: 10, y: 11 })
    mocks.PATCH.mockResolvedValue(
      response(undefined, { detail: 'failed' }, 500),
    )
    await provided.value?.('action', { name: 'Third' })
    expect(node.data.name).toBe('')
    wrapper.unmount()
  })

  it('applies a field edit made during a reload on top of the reloaded state', async () => {
    const node = {
      id: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: '',
        playbookId: null,
        prompt: '',
      },
    } as Node
    const reloadedNode = {
      id: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: '',
        playbookId: null,
        prompt: '',
      },
    } as Node
    const provided = { value: undefined as SaveNodeFields | undefined }
    mocks.findNode.mockReturnValue(node)
    let resolveReload:
      ((value: ReturnType<typeof response>) => void) | undefined
    mocks.GET.mockResolvedValueOnce(response(canvas)).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveReload = resolve
        }),
    )
    const wrapper = mount(FlowCanvas, {
      global: { stubs: { NodePalette: saveProbe(provided) } },
    })
    await flushPromises()
    const load = (
      wrapper.vm as unknown as { loadCanvas: () => Promise<void> }
    ).loadCanvas()
    await flushPromises()
    const save = provided.value?.('action', { name: 'Edited' })
    await flushPromises()
    expect(mocks.PATCH).not.toHaveBeenCalled()
    mocks.findNode.mockReturnValue(reloadedNode)
    resolveReload?.(response(canvas))
    await load
    await save
    expect(reloadedNode.data.name).toBe('Edited')
    expect(mocks.PATCH).toHaveBeenCalledTimes(1)
    expect(mocks.PATCH).toHaveBeenLastCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      {
        params: { path: { kind: 'action', node_id: 'action' } },
        body: { name: 'Edited' },
      },
    )
    expect(await save).toBe(true)
    wrapper.unmount()
  })

  it('keeps queued saves ordered across a reload', async () => {
    const node = {
      id: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: '',
        playbookId: null,
        prompt: '',
      },
    } as Node
    const provided = { value: undefined as SaveNodeFields | undefined }
    mocks.findNode.mockReturnValue(node)
    let resolveFirstSave:
      ((value: ReturnType<typeof response>) => void) | undefined
    let resolveReload:
      ((value: ReturnType<typeof response>) => void) | undefined
    mocks.PATCH.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirstSave = resolve
        }),
    )
    mocks.GET.mockResolvedValueOnce(response(canvas)).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveReload = resolve
        }),
    )
    const wrapper = mount(FlowCanvas, {
      global: { stubs: { NodePalette: saveProbe(provided) } },
    })
    await flushPromises()
    const firstSave = provided.value?.('action', { name: 'First' })
    await flushPromises()
    const load = (
      wrapper.vm as unknown as { loadCanvas: () => Promise<void> }
    ).loadCanvas()
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(1)
    const secondSave = provided.value?.('action', { name: 'Second' })
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledTimes(1)
    resolveFirstSave?.(response(undefined))
    await firstSave
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    expect(mocks.PATCH).toHaveBeenCalledTimes(1)
    resolveReload?.(response(canvas))
    await load
    await secondSave
    expect(mocks.PATCH).toHaveBeenCalledTimes(2)
    expect(mocks.PATCH).toHaveBeenLastCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      {
        params: { path: { kind: 'action', node_id: 'action' } },
        body: { name: 'Second' },
      },
    )
    wrapper.unmount()
  })

  it('reapplies a drag position made during a reload', async () => {
    const node = {
      id: 'trigger',
      position: { x: 1, y: 2 },
      data: { kind: 'trigger' },
    } as Node
    const reloadedNode = {
      id: 'trigger',
      position: { x: 1, y: 2 },
      data: { kind: 'trigger' },
    } as Node
    mocks.findNode.mockReturnValue(node)
    let resolveReload:
      ((value: ReturnType<typeof response>) => void) | undefined
    mocks.GET.mockResolvedValueOnce(response(canvas)).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveReload = resolve
        }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    const load = (
      wrapper.vm as unknown as { loadCanvas: () => Promise<void> }
    ).loadCanvas()
    await flushPromises()
    node.position = { x: 10, y: 11 }
    const save = mocks.handlers.dragStop?.({ node })
    await flushPromises()
    expect(mocks.PATCH).not.toHaveBeenCalled()
    mocks.findNode.mockReturnValue(reloadedNode)
    resolveReload?.(response(canvas))
    await load
    await save
    expect(reloadedNode.position).toEqual({ x: 10, y: 11 })
    expect(mocks.PATCH).toHaveBeenCalledTimes(1)
    expect(mocks.PATCH).toHaveBeenLastCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      {
        params: { path: { kind: 'trigger', node_id: 'trigger' } },
        body: { position: { x: 10, y: 11 } },
      },
    )
    wrapper.unmount()
  })

  it('saves an edit when the reloaded node is missing', async () => {
    const node = {
      id: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: '',
        playbookId: null,
        prompt: '',
      },
    } as Node
    const provided = { value: undefined as SaveNodeFields | undefined }
    mocks.findNode.mockReturnValue(node)
    let resolveReload:
      ((value: ReturnType<typeof response>) => void) | undefined
    mocks.GET.mockResolvedValueOnce(response(canvas)).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveReload = resolve
        }),
    )
    const wrapper = mount(FlowCanvas, {
      global: { stubs: { NodePalette: saveProbe(provided) } },
    })
    await flushPromises()
    const load = (
      wrapper.vm as unknown as { loadCanvas: () => Promise<void> }
    ).loadCanvas()
    await flushPromises()
    const save = provided.value?.('action', { name: 'Edited' })
    await flushPromises()
    mocks.findNode.mockReturnValue(undefined)
    resolveReload?.(
      response({
        trigger_nodes: [],
        action_nodes: [],
        outcome_nodes: [],
        edges: [],
      }),
    )
    await load
    expect(await save).toBe(true)
    expect(mocks.PATCH).toHaveBeenCalledTimes(1)
    expect(mocks.PATCH).toHaveBeenLastCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      {
        params: { path: { kind: 'action', node_id: 'action' } },
        body: { name: 'Edited' },
      },
    )
    wrapper.unmount()
  })

  it('ignores unknown action field nodes', async () => {
    const node = {
      id: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: '',
        playbookId: null,
        prompt: '',
      },
    } as Node
    const provided = { value: undefined as SaveNodeFields | undefined }
    mocks.findNode.mockReturnValue(node)
    const wrapper = mount(FlowCanvas, {
      global: { stubs: { NodePalette: saveProbe(provided) } },
    })
    await flushPromises()
    const newAction = {
      id: 'new-action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: '',
        playbookId: null,
        prompt: '',
      },
    } as Node
    mocks.findNode.mockReturnValue(newAction)
    expect(await provided.value?.('new-action', { name: 'New' })).toBe(true)
    expect(newAction.data.name).toBe('New')
    mocks.findNode.mockReturnValue(undefined)
    expect(await provided.value?.('missing', { name: 'Ignored' })).toBe(false)
    mocks.findNode.mockReturnValue({ id: 'trigger', data: {} })
    expect(await provided.value?.('trigger', { name: 'Ignored' })).toBe(false)
    wrapper.unmount()
  })

  it('waits for in-flight saves before reloading', async () => {
    const node = {
      id: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: '',
        playbookId: null,
        prompt: '',
      },
    } as Node
    const provided = { value: undefined as SaveNodeFields | undefined }
    mocks.findNode.mockReturnValue(node)
    let resolveSave: ((value: ReturnType<typeof response>) => void) | undefined
    mocks.PATCH.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSave = resolve
        }),
    )
    mocks.GET.mockResolvedValueOnce(response(canvas))
    const wrapper = mount(FlowCanvas, {
      global: { stubs: { NodePalette: saveProbe(provided) } },
    })
    await flushPromises()
    const save = provided.value?.('action', { name: 'Edited' })
    await flushPromises()
    const load = (
      wrapper.vm as unknown as {
        loadCanvas: () => Promise<void>
      }
    ).loadCanvas()
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(1)
    resolveSave?.(response(undefined, { detail: 'failed' }, 500))
    await save
    await load
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    expect(node.data.name).toBe('')
    wrapper.unmount()
  })

  it('continues after a rejected action save chain', async () => {
    const node = {
      id: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        name: '',
        playbookId: null,
        prompt: '',
      },
    } as Node
    const provided = { value: undefined as SaveNodeFields | undefined }
    mocks.findNode.mockReturnValueOnce(node).mockImplementation(() => {
      throw new Error('down')
    })
    mocks.PATCH.mockResolvedValue(
      response(undefined, { detail: 'failed' }, 500),
    )
    const wrapper = mount(FlowCanvas, {
      global: { stubs: { NodePalette: saveProbe(provided) } },
    })
    await flushPromises()
    await expect(provided.value?.('action', { name: 'First' })).rejects.toThrow(
      'down',
    )
    wrapper.unmount()
  })

  it('reloads the canvas after a failed node delete', async () => {
    const refetched = {
      trigger_nodes: [],
      action_nodes: [
        {
          id: 'action',
          kind: 'action',
          position: { x: 3, y: 4 },
          name: '',
          playbook_id: null,
          prompt: '',
          enabled: false,
          sync_status: 'unprovisioned',
          sync_error: null,
          invocation_count: 2,
        },
      ],
      outcome_nodes: [],
      edges: [],
    }
    mocks.GET.mockResolvedValueOnce(response(canvas)).mockResolvedValueOnce(
      response(refetched),
    )
    mocks.DELETE.mockResolvedValue(
      response(undefined, { detail: 'delete failed' }, 500),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    expect(vueFlow(wrapper).props('nodes')).toEqual([
      {
        id: 'action',
        type: 'action',
        position: { x: 3, y: 4 },
        data: {
          kind: 'action',
          label: 'Action',
          name: '',
          playbookId: null,
          prompt: '',
          enabled: false,
          syncStatus: 'unprovisioned',
          syncError: null,
          invocationCount: 2,
        },
      },
    ])
    expect(vueFlow(wrapper).props('edges')).toEqual([])
    wrapper.unmount()
  })

  it('refreshes Action sync state after deleting a Trigger', async () => {
    const refreshed = {
      ...canvas,
      action_nodes: [
        {
          ...canvas.action_nodes[0],
          sync_status: 'disabled',
        },
      ],
    }
    mocks.GET.mockResolvedValueOnce(response(canvas)).mockResolvedValueOnce(
      response(refreshed),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.findNode.mockImplementation((id: string) =>
      (vueFlow(wrapper).props('nodes') as Node[]).find(
        (node) => node.id === id,
      ),
    )
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    expect(vueFlow(wrapper).props('nodes')).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: 'action',
          data: expect.objectContaining({ syncStatus: 'disabled' }),
        }),
      ]),
    )
    wrapper.unmount()
  })

  it('does not refresh sync state after deleting an Outcome', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'outcome' }])
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('adds a created node after a reload that started before its POST', async () => {
    const refetched = {
      trigger_nodes: [],
      action_nodes: [],
      outcome_nodes: [],
      edges: [],
    }
    let resolveReload:
      ((value: ReturnType<typeof response>) => void) | undefined
    mocks.GET.mockResolvedValueOnce(response(canvas)).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveReload = resolve
        }),
    )
    mocks.DELETE.mockResolvedValue(
      response(undefined, { detail: 'delete failed' }, 500),
    )
    let resolvePost: ((value: ReturnType<typeof response>) => void) | undefined
    mocks.POST.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolvePost = resolve
        }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    const dropZone = wrapper.find('[data-testid="canvas-drop-zone"]')
    const dataTransfer = {
      types: [NODE_KIND_MIME],
      getData: vi.fn().mockReturnValue('action'),
      dropEffect: '',
    }
    const drop = new Event('drop', { bubbles: true, cancelable: true })
    Object.defineProperty(drop, 'dataTransfer', { value: dataTransfer })
    Object.defineProperty(drop, 'clientX', { value: 100 })
    Object.defineProperty(drop, 'clientY', { value: 200 })
    dropZone.element.dispatchEvent(drop)
    await flushPromises()
    expect(mocks.POST).toHaveBeenCalled()
    expect(mocks.addNodes).not.toHaveBeenCalled()
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    resolvePost?.(
      response({
        id: 'new',
        kind: 'action',
        position: { x: 0, y: 0 },
        name: '',
        playbook_id: null,
        prompt: '',
        enabled: false,
        sync_status: 'unprovisioned',
        sync_error: null,
      }),
    )
    await flushPromises()
    expect(mocks.addNodes).not.toHaveBeenCalled()
    resolveReload?.(response(refetched))
    await flushPromises()
    expect(mocks.addNodes).toHaveBeenCalledTimes(1)
    mocks.DELETE.mockResolvedValue(response(undefined))
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'new' }])
    await flushPromises()
    expect(mocks.DELETE).toHaveBeenLastCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      { params: { path: { kind: 'action', node_id: 'new' } } },
    )
    wrapper.unmount()
  })

  it('does not duplicate a created node included in a reload', async () => {
    const refetched = {
      trigger_nodes: [],
      action_nodes: [
        {
          id: 'new',
          kind: 'action',
          position: { x: 0, y: 0 },
          name: '',
          playbook_id: null,
          prompt: '',
          enabled: false,
          sync_status: 'unprovisioned',
          sync_error: null,
          invocation_count: 2,
        },
      ],
      outcome_nodes: [],
      edges: [],
    }
    let resolveReload:
      ((value: ReturnType<typeof response>) => void) | undefined
    mocks.GET.mockResolvedValueOnce(response(canvas)).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveReload = resolve
        }),
    )
    mocks.DELETE.mockResolvedValue(
      response(undefined, { detail: 'delete failed' }, 500),
    )
    let resolvePost: ((value: ReturnType<typeof response>) => void) | undefined
    mocks.POST.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolvePost = resolve
        }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    const drop = new Event('drop', { bubbles: true, cancelable: true })
    Object.defineProperty(drop, 'dataTransfer', {
      value: {
        types: [NODE_KIND_MIME],
        getData: vi.fn().mockReturnValue('action'),
        dropEffect: '',
      },
    })
    Object.defineProperty(drop, 'clientX', { value: 100 })
    Object.defineProperty(drop, 'clientY', { value: 200 })
    wrapper.find('[data-testid="canvas-drop-zone"]').element.dispatchEvent(drop)
    await flushPromises()
    expect(mocks.POST).toHaveBeenCalled()
    expect(mocks.addNodes).not.toHaveBeenCalled()
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    resolvePost?.(
      response({
        id: 'new',
        kind: 'action',
        position: { x: 0, y: 0 },
        name: '',
        playbook_id: null,
        prompt: '',
        enabled: false,
        sync_status: 'unprovisioned',
        sync_error: null,
      }),
    )
    await flushPromises()
    expect(mocks.addNodes).not.toHaveBeenCalled()
    mocks.findNode.mockReturnValue({
      id: 'new',
      type: 'action',
      position: { x: 0, y: 0 },
      data: { kind: 'action', label: 'Action' },
    })
    resolveReload?.(response(refetched))
    await flushPromises()
    expect(mocks.addNodes).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('does not add a created node when the reload fails', async () => {
    let rejectReload: ((reason?: unknown) => void) | undefined
    mocks.GET.mockResolvedValueOnce(response(canvas)).mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          rejectReload = reject
        }),
    )
    mocks.DELETE.mockResolvedValue(
      response(undefined, { detail: 'delete failed' }, 500),
    )
    let resolvePost: ((value: ReturnType<typeof response>) => void) | undefined
    mocks.POST.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolvePost = resolve
        }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    const drop = new Event('drop', { bubbles: true, cancelable: true })
    Object.defineProperty(drop, 'dataTransfer', {
      value: {
        types: [NODE_KIND_MIME],
        getData: vi.fn().mockReturnValue('action'),
        dropEffect: '',
      },
    })
    Object.defineProperty(drop, 'clientX', { value: 100 })
    Object.defineProperty(drop, 'clientY', { value: 200 })
    wrapper.find('[data-testid="canvas-drop-zone"]').element.dispatchEvent(drop)
    await flushPromises()
    expect(mocks.POST).toHaveBeenCalled()
    expect(mocks.addNodes).not.toHaveBeenCalled()
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    resolvePost?.(
      response({
        id: 'new',
        kind: 'action',
        position: { x: 0, y: 0 },
        name: '',
        playbook_id: null,
        prompt: '',
        enabled: false,
        sync_status: 'unprovisioned',
        sync_error: null,
      }),
    )
    await flushPromises()
    expect(mocks.addNodes).not.toHaveBeenCalled()
    rejectReload?.(new Error('down'))
    await flushPromises()
    expect(mocks.addNodes).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="load-error"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('skips cascaded edge deletes when removing a node', async () => {
    mocks.GET.mockResolvedValue(
      response({
        ...canvas,
        edges: [
          canvas.edges[0],
          {
            id: 'outcome-edge',
            source: { id: 'action', kind: 'action' },
            target: { id: 'outcome', kind: 'outcome' },
          },
        ],
      }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.handlers.edgesChange?.([
      { type: 'remove', id: 'edge' },
      { type: 'remove', id: 'outcome-edge' },
    ])
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'action' }])
    await flushPromises()
    expect(mocks.DELETE).toHaveBeenCalledTimes(1)
    expect(mocks.DELETE).toHaveBeenCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      { params: { path: { kind: 'action', node_id: 'action' } } },
    )
    wrapper.unmount()
  })

  it('reloads the surviving graph when one node delete fails', async () => {
    const refetched = {
      trigger_nodes: [],
      action_nodes: [
        {
          id: 'action',
          kind: 'action',
          position: { x: 3, y: 4 },
          name: '',
          playbook_id: null,
          prompt: '',
          enabled: false,
          sync_status: 'unprovisioned',
          sync_error: null,
          invocation_count: 2,
        },
      ],
      outcome_nodes: [],
      edges: [],
    }
    mocks.GET.mockResolvedValueOnce(response(canvas))
      .mockResolvedValueOnce(response(canvas))
      .mockResolvedValueOnce(response(refetched))
    mocks.DELETE.mockResolvedValueOnce(
      response(undefined),
    ).mockResolvedValueOnce(
      response(undefined, { detail: 'delete failed' }, 500),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.handlers.nodesChange?.([
      { type: 'remove', id: 'trigger' },
      { type: 'remove', id: 'action' },
    ])
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(3)
    expect(vueFlow(wrapper).props('nodes')).toHaveLength(1)
    expect(vueFlow(wrapper).props('nodes')[0]).toEqual({
      id: 'action',
      type: 'action',
      position: { x: 3, y: 4 },
      data: {
        kind: 'action',
        label: 'Action',
        name: '',
        playbookId: null,
        prompt: '',
        enabled: false,
        syncStatus: 'unprovisioned',
        syncError: null,
        invocationCount: 2,
      },
    })
    expect(vueFlow(wrapper).props('edges')).toEqual([])
    wrapper.unmount()
  })

  it('reloads both nodes and edges when both node deletes fail', async () => {
    mocks.GET.mockResolvedValueOnce(response(canvas)).mockResolvedValueOnce(
      response(canvas),
    )
    mocks.DELETE.mockResolvedValue(
      response(undefined, { detail: 'delete failed' }, 500),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.handlers.nodesChange?.([
      { type: 'remove', id: 'trigger' },
      { type: 'remove', id: 'action' },
    ])
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    expect(vueFlow(wrapper).props('nodes')).toHaveLength(3)
    expect(vueFlow(wrapper).props('edges')).toHaveLength(1)
    wrapper.unmount()
  })

  it('treats node delete 404 and thrown errors as expected', async () => {
    mocks.GET.mockResolvedValueOnce(
      response({
        ...canvas,
        edges: [
          canvas.edges[0],
          {
            id: 'outcome-edge',
            source: { id: 'action', kind: 'action' },
            target: { id: 'outcome', kind: 'outcome' },
          },
        ],
      }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.DELETE.mockResolvedValue(
      response(undefined, { detail: 'not found' }, 404),
    )
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(1)
    mocks.DELETE.mockRejectedValue({ status: 404 })
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    mocks.DELETE.mockRejectedValue(new Error('down'))
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(3)
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
    mocks.DELETE.mockResolvedValue(
      response(undefined, { detail: 'delete failed' }, 500),
    )
    mocks.handlers.edgesChange?.([{ type: 'remove', id: 'edge' }])
    await flushPromises()
    expect(mocks.DELETE).toHaveBeenCalledWith('/api/canvas/edges/{edge_id}', {
      params: { path: { edge_id: 'edge' } },
    })
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
    mocks.GET.mockResolvedValueOnce(
      response(undefined, { detail: 'refresh failed' }),
    )
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

  it('refreshes action synchronization after creating an edge', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    const nodes = vueFlow(wrapper).props('nodes') as Node[]
    const action = nodes.find((node) => node.id === 'action')
    mocks.findNode.mockImplementation((id: string) =>
      nodes.find((node) => node.id === id),
    )
    mocks.POST.mockResolvedValue(
      response({
        id: 'new-edge',
        source: { id: 'trigger', kind: 'trigger' },
        target: { id: 'action', kind: 'action' },
      }),
    )
    mocks.GET.mockResolvedValueOnce(
      response({
        ...canvas,
        action_nodes: [
          {
            ...canvas.action_nodes[0],
            enabled: true,
            sync_status: 'enabled',
          },
          {
            ...canvas.action_nodes[0],
            id: 'unknown',
          },
        ],
      }),
    )
    await mocks.handlers.connect?.({ source: 'action', target: 'outcome' })
    expect(action?.data).toMatchObject({
      enabled: true,
      syncStatus: 'enabled',
      syncError: null,
    })
    mocks.GET.mockRejectedValueOnce(new Error('refresh failed'))
    await mocks.handlers.connect?.({ source: 'action', target: 'outcome' })
    await flushPromises()
    await flushPromises()
    vi.runAllTimers()
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
    ) as (connection: {
      id?: string
      source: string
      target: string
    }) => boolean
    expect(isValid({ source: 'action', target: 'outcome' })).toBe(true)
    expect(isValid({ source: 'trigger', target: 'action' })).toBe(false)
    expect(isValid({ id: 'edge', source: 'trigger', target: 'action' })).toBe(
      true,
    )
    expect(isValid({ id: 'other', source: 'trigger', target: 'action' })).toBe(
      false,
    )
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

  it('labels Trigger to Action edges with the invocation count', async () => {
    mocks.GET.mockResolvedValueOnce(
      response({
        ...canvas,
        action_nodes: [{ ...canvas.action_nodes[0], invocation_count: 1 }],
        edges: [
          ...canvas.edges,
          {
            id: 'action-outcome',
            source: { id: 'action', kind: 'action' },
            target: { id: 'outcome', kind: 'outcome' },
          },
        ],
      }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    expect(vueFlow(wrapper).props('edges')).toEqual([
      expect.objectContaining({ id: 'edge', label: '1 invocation' }),
      expect.objectContaining({ id: 'action-outcome', label: '0 outcomes' }),
    ])
    wrapper.unmount()
  })

  it('refreshes invocations on demand and reloads the canvas', async () => {
    mocks.GET.mockResolvedValueOnce(response(canvas)).mockResolvedValueOnce(
      response({
        ...canvas,
        action_nodes: [{ ...canvas.action_nodes[0], invocation_count: 5 }],
      }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    const button = wrapper.find('[data-testid="refresh-invocations"]')
    expect(button.attributes('title')).toBe('Refresh invocations')
    let finish: (value: unknown) => void = () => {}
    mocks.POST.mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    await button.trigger('click')
    expect(button.attributes('disabled')).toBeDefined()
    await button.trigger('click')
    finish(response({ listed: 1, upserted: 1, refreshed: 0 }))
    await flushPromises()
    expect(button.attributes('disabled')).toBeUndefined()
    expect(mocks.POST).toHaveBeenCalledTimes(1)
    expect(mocks.POST).toHaveBeenCalledWith('/api/invocations/refresh')
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    expect(vueFlow(wrapper).props('edges')).toEqual([
      expect.objectContaining({ id: 'edge', label: '5 invocations' }),
    ])
    wrapper.unmount()
  })

  it('reloads the canvas even when the refresh request fails', async () => {
    mocks.POST.mockRejectedValueOnce(new Error('refresh failed'))
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    await wrapper.find('[data-testid="refresh-invocations"]').trigger('click')
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('updates edge labels when Action sync state is refreshed', async () => {
    mocks.GET.mockResolvedValueOnce(response(canvas)).mockResolvedValueOnce(
      response({
        ...canvas,
        action_nodes: [{ ...canvas.action_nodes[0], invocation_count: 3 }],
      }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.getEdges.value).toEqual([
      expect.objectContaining({ id: 'edge', label: '3 invocations' }),
    ])
    wrapper.unmount()
  })

  it('labels Action to Outcome edges with the outcome count', async () => {
    mocks.GET.mockResolvedValueOnce(
      response({
        ...canvas,
        edges: [
          ...canvas.edges,
          {
            id: 'action-outcome',
            source: { id: 'action', kind: 'action' },
            target: { id: 'outcome', kind: 'outcome' },
            outcome_count: 1,
          },
        ],
      }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    expect(vueFlow(wrapper).props('edges')).toEqual([
      expect.objectContaining({ id: 'edge', label: '2 invocations' }),
      expect.objectContaining({ id: 'action-outcome', label: '1 outcome' }),
    ])
    wrapper.unmount()
  })

  it('updates Outcome edge labels when sync state is refreshed', async () => {
    const outcomeEdge = {
      id: 'action-outcome',
      source: { id: 'action', kind: 'action' },
      target: { id: 'outcome', kind: 'outcome' },
      outcome_count: 1,
    }
    mocks.GET.mockResolvedValueOnce(
      response({ ...canvas, edges: [...canvas.edges, outcomeEdge] }),
    ).mockResolvedValueOnce(
      response({
        ...canvas,
        edges: [
          { ...canvas.edges[0], outcome_count: null },
          { ...outcomeEdge, outcome_count: 5 },
          {
            id: 'detached-outcome',
            source: { id: 'action', kind: 'action' },
            target: { id: 'gone', kind: 'outcome' },
            outcome_count: 7,
          },
          {
            id: 'unset-outcome',
            source: { id: 'action', kind: 'action' },
            target: { id: 'unset', kind: 'outcome' },
            outcome_count: null,
          },
        ],
      }),
    )
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.getEdges.value.push(
      {
        id: 'action-outcome',
        source: 'action',
        target: 'outcome',
        data: { sourceKind: 'action', targetKind: 'outcome' },
        label: '1 outcome',
      },
      {
        id: 'unset-outcome',
        source: 'action',
        target: 'unset',
        data: { sourceKind: 'action', targetKind: 'outcome' },
        label: 'stale',
      },
    )
    mocks.handlers.nodesChange?.([{ type: 'remove', id: 'trigger' }])
    await flushPromises()
    expect(mocks.getEdges.value).toEqual([
      expect.objectContaining({ id: 'edge', label: '2 invocations' }),
      expect.objectContaining({ id: 'action-outcome', label: '5 outcomes' }),
      expect.objectContaining({ id: 'unset-outcome', label: '0 outcomes' }),
    ])
    wrapper.unmount()
  })

  it('opens the outcome sheet when an outcome edge is clicked', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.findNode.mockReturnValue({
      id: 'outcome',
      data: { kind: 'outcome', outcome: { kind: 'duplicate' } },
    } as Node)
    mocks.handlers.edgeClick?.({
      edge: {
        source: 'action',
        target: 'outcome',
        data: { sourceKind: 'action', targetKind: 'outcome' },
      },
    })
    await flushPromises()
    expect(mocks.sheetProps).toMatchObject({
      open: true,
      nodeId: 'outcome',
      actionNodeId: 'action',
      kind: 'duplicate',
    })
    expect(wrapper.find('[data-testid="outcome-sheet-stub"]').exists()).toBe(
      true,
    )
    wrapper.unmount()
  })

  it('closes the outcome sheet when it is dismissed', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.findNode.mockReturnValue({
      id: 'outcome',
      data: { kind: 'outcome', outcome: { kind: 'duplicate' } },
    } as Node)
    mocks.handlers.edgeClick?.({
      edge: {
        source: 'action',
        target: 'outcome',
        data: { sourceKind: 'action', targetKind: 'outcome' },
      },
    })
    await flushPromises()
    expect(mocks.sheetProps.open).toBe(true)
    wrapper
      .findComponent({ name: 'OutcomeInvocationsSheet' })
      .vm.$emit('update:open', false)
    await flushPromises()
    expect(mocks.sheetProps.open).toBe(false)
    wrapper.unmount()
  })

  it('opens the sheet with a null kind for outcomes without one', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.findNode.mockReturnValue({
      id: 'outcome',
      data: { kind: 'outcome' },
    } as Node)
    mocks.handlers.edgeClick?.({
      edge: {
        source: 'action',
        target: 'outcome',
        data: { sourceKind: 'action', targetKind: 'outcome' },
      },
    })
    await flushPromises()
    expect(mocks.sheetProps).toMatchObject({
      open: true,
      nodeId: 'outcome',
      kind: null,
    })
    wrapper.unmount()
  })

  it('ignores edge clicks on non-outcome edges', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    mocks.handlers.edgeClick?.({
      edge: {
        source: 'trigger',
        target: 'action',
        data: { sourceKind: 'trigger', targetKind: 'action' },
      },
    })
    mocks.handlers.edgeClick?.({
      edge: { source: 'trigger', target: 'action' },
    })
    await flushPromises()
    expect(mocks.sheetProps?.open).not.toBe(true)
    wrapper.unmount()
  })

  it('does not register a node click handler', async () => {
    const wrapper = mount(FlowCanvas)
    await flushPromises()
    expect(
      (mocks.handlers as Record<string, unknown>).nodeClick,
    ).toBeUndefined()
    expect(mocks.sheetProps?.open).not.toBe(true)
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
