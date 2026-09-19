import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Component } from 'vue'

const mocks = vi.hoisted(() => ({
  removeNodes: vi.fn(),
  updateNodeData: vi.fn(),
  GET: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  client: { GET: mocks.GET },
}))

vi.mock('@vue-flow/core', () => ({
  Handle: defineComponent({
    name: 'CanvasHandle',
    props: {
      type: { type: String, required: true },
      position: { type: String, required: true },
    },
    setup(props) {
      return () =>
        h('span', {
          class: 'handle',
          'data-type': props.type,
          'data-position': props.position,
        })
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
    name: 'NodeToolbar',
    setup:
      (_, { slots }) =>
      () =>
        h('div', { class: 'node-toolbar' }, slots.default?.()),
  }),
}))

import ActionNode from '@/components/nodes/ActionNode.vue'
import OutcomeNode from '@/components/nodes/OutcomeNode.vue'
import TriggerNode from '@/components/nodes/TriggerNode.vue'
import { nodeTypes } from '@/components/nodes/nodeTypes'
import { isNodeKind, nodeAccentClass } from '@/lib/nodeKinds'

const components = [
  {
    component: TriggerNode,
    kind: 'trigger',
    hint: 'Choose repository and event',
    handles: ['source'],
  },
  {
    component: ActionNode,
    kind: 'action',
    hint: 'Choose a Playbook',
    handles: ['target', 'source'],
  },
  {
    component: OutcomeNode,
    kind: 'outcome',
    hint: 'Choose an Outcome kind',
    handles: ['target'],
  },
] as const

function mountNode(component: Component) {
  const props =
    component === TriggerNode
      ? {
          id: 'n1',
          data: {
            kind: 'trigger',
            label: 'Trigger',
            trigger: { event_action: null, repository_full_name: null },
          },
        }
      : { id: 'n1' }
  return mount(component, { props } as never)
}

describe('canvas nodes', () => {
  beforeEach(() => {
    mocks.removeNodes.mockReset()
    mocks.updateNodeData.mockReset()
    mocks.GET.mockResolvedValue({
      data: [],
      error: undefined,
    })
  })

  it.each(components)(
    'renders the incomplete $kind node with its handles',
    async ({ component, kind, hint, handles }) => {
      const wrapper = mountNode(component)
      await flushPromises()
      const node = wrapper.find('[data-testid="canvas-node"]')
      expect(node.attributes('data-kind')).toBe(kind)
      expect(node.attributes('data-incomplete')).toBe('true')
      expect(node.text()).toContain(`${kind[0].toUpperCase()}${kind.slice(1)}`)
      expect(node.text()).toContain('Incomplete')
      expect(node.text()).toContain(hint)
      expect(
        wrapper
          .findAll('.handle')
          .map((handle) => handle.attributes('data-type')),
      ).toEqual(handles)
      await wrapper.find('[data-testid="delete-node"]').trigger('click')
      expect(mocks.removeNodes).toHaveBeenCalledWith(['n1'])
      wrapper.unmount()
    },
  )

  it('maps node kinds to their custom components', () => {
    expect(nodeTypes.trigger).toBe(TriggerNode)
    expect(nodeTypes.action).toBe(ActionNode)
    expect(nodeTypes.outcome).toBe(OutcomeNode)
  })

  it('rejects unknown node kinds', () => {
    expect(isNodeKind('bogus')).toBe(false)
  })

  it('maps node kinds to their accent classes', () => {
    expect(nodeAccentClass('trigger')).toBe('border-l-sky-500')
    expect(nodeAccentClass('action')).toBe('border-l-violet-500')
    expect(nodeAccentClass('outcome')).toBe('border-l-emerald-500')
  })
})
