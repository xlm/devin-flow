import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { Position, type EdgeProps, type GraphNode } from '@vue-flow/core'
import CountEdge from '@/components/edges/CountEdge.vue'

const getSmoothStepPath = vi.hoisted(() =>
  vi.fn(() => ['M 0 0', 10, 20] as [string, number, number]),
)

vi.mock('@vue-flow/core', () => ({
  BaseEdge: defineComponent({
    name: 'BaseEdge',
    props: {
      id: { type: String },
      path: { type: String },
      label: { type: String },
      labelX: { type: Number },
      labelY: { type: Number },
    },
    setup:
      (_, { attrs }) =>
      () =>
        h('div', attrs),
  }),
  Position: {
    Bottom: 'bottom',
    Left: 'left',
    Right: 'right',
    Top: 'top',
  },
  getSmoothStepPath,
}))

const baseProps: EdgeProps = {
  id: 'edge',
  source: 'source',
  target: 'target',
  sourceNode: {} as GraphNode,
  targetNode: {} as GraphNode,
  sourceX: 1,
  sourceY: 2,
  sourcePosition: Position.Bottom,
  targetX: 40,
  targetY: 50,
  targetPosition: Position.Right,
  type: 'smoothstep',
  markerStart: '',
  markerEnd: '',
  data: {},
  events: {} as EdgeProps['events'],
  label: '2 outcomes',
}

describe('CountEdge', () => {
  it('places horizontal labels on the final segment', () => {
    const wrapper = mount(CountEdge, {
      props: baseProps,
    })
    const baseEdge = wrapper.findComponent({ name: 'BaseEdge' })
    expect(getSmoothStepPath).toHaveBeenCalled()
    expect(baseEdge.props()).toMatchObject({
      id: 'edge',
      path: 'M 0 0',
      label: '2 outcomes',
      labelX: 25,
      labelY: 50,
    })
  })

  it('places vertical labels on the final segment', () => {
    const wrapper = mount(CountEdge, {
      props: {
        ...baseProps,
        targetPosition: Position.Bottom,
      },
    })
    const baseEdge = wrapper.findComponent({ name: 'BaseEdge' })
    expect(baseEdge.props()).toMatchObject({
      labelX: 40,
      labelY: 35,
    })
  })
})
