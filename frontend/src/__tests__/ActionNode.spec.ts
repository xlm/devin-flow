import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref, type InjectionKey } from 'vue'
import type { Edge } from '@vue-flow/core'
import ActionNode from '@/components/nodes/ActionNode.vue'
import { resetPlaybooksCache } from '@/composables/usePlaybooks'
import { SAVE_NODE_FIELDS, type SaveNodeFields } from '@/lib/canvasInjection'

const GET = vi.hoisted(() => vi.fn())

vi.mock('@/api/client', () => ({
  client: { GET },
}))

const edges = ref<Edge[]>([])

vi.mock('@vue-flow/core', () => ({
  Handle: defineComponent({
    props: { type: { type: String }, position: { type: String } },
    setup: (props) => () => h('span', props),
  }),
  Position: { Left: 'left', Right: 'right', Top: 'top' },
  useVueFlow: () => ({ removeNodes: vi.fn(), edges }),
}))

vi.mock('@vue-flow/node-toolbar', () => ({
  NodeToolbar: defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.()),
  }),
}))

function mountAction(
  data: Record<string, unknown> = {},
  saver?: SaveNodeFields,
) {
  return mount(ActionNode, {
    props: { id: 'n1', data } as never,
    global: {
      provide: saver
        ? { [SAVE_NODE_FIELDS as InjectionKey<SaveNodeFields>]: saver }
        : {},
    },
  })
}

describe('ActionNode', () => {
  afterEach(() => {
    resetPlaybooksCache()
    GET.mockReset()
    edges.value = []
  })

  it('renders field values and saves edits', async () => {
    GET.mockResolvedValue({
      data: [{ id: 'pb-1', title: 'Triage' }],
      error: undefined,
    })
    const save = vi.fn().mockResolvedValue(undefined)
    const wrapper = mountAction(
      {
        name: 'Triage action',
        playbookId: 'pb-1',
        extraInstructions: 'Notes',
      },
      save,
    )
    await flushPromises()
    expect(
      (wrapper.get('[data-testid="action-name"]').element as HTMLInputElement)
        .value,
    ).toBe('Triage action')
    expect(
      (
        wrapper.get('[data-testid="action-playbook"]')
          .element as HTMLSelectElement
      ).value,
    ).toBe('pb-1')
    expect(
      (
        wrapper.get('[data-testid="action-instructions"]')
          .element as HTMLTextAreaElement
      ).value,
    ).toBe('Notes')
    await wrapper.get('[data-testid="action-name"]').setValue('Updated')
    await wrapper.get('[data-testid="action-name"]').trigger('change')
    await wrapper.get('[data-testid="action-playbook"]').setValue('pb-1')
    await wrapper.get('[data-testid="action-playbook"]').trigger('change')
    await wrapper.get('[data-testid="action-instructions"]').setValue('More')
    await wrapper.get('[data-testid="action-instructions"]').trigger('change')
    expect(save).toHaveBeenCalledWith('n1', { name: 'Updated' })
    expect(save).toHaveBeenCalledWith('n1', { playbookId: 'pb-1' })
    expect(save).toHaveBeenCalledWith('n1', { extraInstructions: 'More' })
  })

  it('saves null when the playbook placeholder is selected', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const save = vi.fn().mockResolvedValue(undefined)
    const wrapper = mountAction({ name: 'Triage', playbookId: 'pb-1' }, save)
    await flushPromises()
    await wrapper.get('[data-testid="action-playbook"]').setValue('')
    await wrapper.get('[data-testid="action-playbook"]').trigger('change')
    expect(save).toHaveBeenCalledWith('n1', { playbookId: null })
  })

  it('marks a complete action with a trigger as complete', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    edges.value = [
      {
        id: 'edge',
        source: 'trigger',
        target: 'n1',
        data: { sourceKind: 'trigger' },
      },
    ]
    const wrapper = mountAction({ name: 'Triage', playbookId: 'pb-1' })
    await flushPromises()
    expect(
      wrapper.get('[data-testid="canvas-node"]').attributes('data-incomplete'),
    ).toBe('false')
    expect(
      wrapper.get('[data-testid="canvas-node"]').attributes('data-status'),
    ).toBe('Ready')
    expect(wrapper.text()).toContain('Ready')
  })

  it('shows no trigger status for a complete unlinked action', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountAction({ name: 'Triage', playbookId: 'pb-1' })
    await flushPromises()
    expect(
      wrapper.get('[data-testid="canvas-node"]').attributes('data-incomplete'),
    ).toBe('true')
    expect(wrapper.text()).toContain('No Trigger')
  })

  it('keeps whitespace-only names incomplete', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountAction({ name: '  ', playbookId: 'pb-1' })
    await flushPromises()
    expect(
      wrapper.get('[data-testid="canvas-node"]').attributes('data-incomplete'),
    ).toBe('true')
    expect(wrapper.text()).toContain('Incomplete')
  })

  it('preserves an unknown selected playbook', async () => {
    GET.mockResolvedValue({
      data: [{ id: 'pb-1', title: 'Triage' }],
      error: undefined,
    })
    const wrapper = mountAction({ name: 'Triage', playbookId: 'missing' })
    await flushPromises()
    const option = wrapper.get('option[value="missing"]')
    expect(option.text()).toBe('Unknown Playbook (missing)')
    expect(
      (
        wrapper.get('[data-testid="action-playbook"]')
          .element as HTMLSelectElement
      ).value,
    ).toBe('missing')
  })

  it('shows playbook loading and error retry states', async () => {
    let resolve: ((value: unknown) => void) | undefined
    GET.mockImplementationOnce(
      () =>
        new Promise((result) => {
          resolve = result
        }),
    ).mockResolvedValueOnce({ data: [], error: undefined })
    const loadingWrapper = mountAction()
    expect(loadingWrapper.text()).toContain('Loading Playbooks...')
    resolve?.({ data: undefined, error: { detail: 'down' } })
    await flushPromises()
    expect(
      loadingWrapper.find('[data-testid="playbooks-retry"]').exists(),
    ).toBe(true)
    await loadingWrapper.get('[data-testid="playbooks-retry"]').trigger('click')
    expect(GET).toHaveBeenCalledTimes(2)
  })

  it('disables the future automation switch', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountAction()
    await flushPromises()
    const button = wrapper.get('[data-testid="enable-switch"]')
    expect((button.element as HTMLButtonElement).disabled).toBe(true)
    expect(button.attributes('title')).toBe(
      'Enabling the Automation activates in a later ticket',
    )
  })

  it('works without an injected saver', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountAction()
    await flushPromises()
    await wrapper.get('[data-testid="action-name"]').setValue('Updated')
    await expect(
      wrapper.get('[data-testid="action-name"]').trigger('change'),
    ).resolves.not.toThrow()
  })
})
