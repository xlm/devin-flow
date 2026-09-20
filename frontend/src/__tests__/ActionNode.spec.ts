import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, ref, type InjectionKey } from 'vue'
import type { Edge } from '@vue-flow/core'
import ActionNode from '@/components/nodes/ActionNode.vue'
import { resetPlaybooksCache } from '@/composables/usePlaybooks'
import { SAVE_NODE_FIELDS, type SaveNodeFields } from '@/lib/canvasInjection'

const GET = vi.hoisted(() => vi.fn())
const findNode = vi.hoisted(() => vi.fn())

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
  useVueFlow: () => ({ removeNodes: vi.fn(), edges, findNode }),
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
    findNode.mockReset()
    edges.value = []
  })

  it('renders field values and saves edits', async () => {
    GET.mockResolvedValue({
      data: [{ id: 'pb-1', title: 'Triage' }],
      error: undefined,
    })
    const save = vi.fn().mockResolvedValue(true)
    const wrapper = mountAction(
      {
        name: 'Triage action',
        playbookId: 'pb-1',
        prompt: 'Notes',
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
        wrapper.get('[data-testid="action-prompt"]')
          .element as HTMLTextAreaElement
      ).value,
    ).toBe('Notes')
    expect(
      wrapper.get('[data-testid="action-name"]').attributes('maxlength'),
    ).toBe('200')
    expect(
      wrapper.get('[data-testid="action-name"]').attributes('placeholder'),
    ).toBe('Name')
    expect(
      wrapper.get('[data-testid="action-prompt"]').attributes('maxlength'),
    ).toBe('20000')
    expect(
      wrapper.get('[data-testid="action-prompt"]').attributes('placeholder'),
    ).toBe('Enter prompt here')
    await wrapper.get('[data-testid="action-name"]').setValue('Updated')
    await wrapper.get('[data-testid="action-name"]').trigger('change')
    await wrapper.get('[data-testid="action-playbook"]').setValue('pb-1')
    await wrapper.get('[data-testid="action-playbook"]').trigger('change')
    await wrapper.get('[data-testid="action-prompt"]').setValue('More')
    await wrapper.get('[data-testid="action-prompt"]').trigger('change')
    expect(save).toHaveBeenCalledWith('n1', { name: 'Updated' })
    expect(save).toHaveBeenCalledWith('n1', { playbookId: 'pb-1' })
    expect(save).toHaveBeenCalledWith('n1', { prompt: 'More' })
  })

  it('keeps typed text across a re-render', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const save = vi.fn().mockResolvedValue(true)
    const data = { name: '', playbookId: null, prompt: '' }
    const wrapper = mountAction(data, save)
    await flushPromises()
    const name = wrapper.get('[data-testid="action-name"]')
    const prompt = wrapper.get('[data-testid="action-prompt"]')
    ;(name.element as HTMLInputElement).value = 'Triage issue'
    await name.trigger('input')
    ;(prompt.element as HTMLTextAreaElement).value = 'Handle the issue'
    await prompt.trigger('input')
    await wrapper.setProps({ data: { ...data, syncStatus: 'pending' } })
    expect((name.element as HTMLInputElement).value).toBe('Triage issue')
    expect((prompt.element as HTMLTextAreaElement).value).toBe(
      'Handle the issue',
    )
    await name.trigger('change')
    await prompt.trigger('change')
    expect(save).toHaveBeenCalledWith('n1', { name: 'Triage issue' })
    expect(save).toHaveBeenCalledWith('n1', { prompt: 'Handle the issue' })
    await wrapper.setProps({
      data: {
        ...data,
        name: 'Saved name',
        prompt: 'Saved prompt',
      },
    })
    expect((name.element as HTMLInputElement).value).toBe('Saved name')
    expect((prompt.element as HTMLTextAreaElement).value).toBe('Saved prompt')
  })

  it('saves null when the playbook placeholder is selected', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const save = vi.fn().mockResolvedValue(true)
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
    findNode.mockReturnValue({
      id: 'trigger',
      data: {
        trigger: {
          event_action: 'opened',
          repository_full_name: 'octo/repo',
        },
      },
    })
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
    expect(wrapper.text()).toContain('Connect a Trigger to this Action')
    expect(wrapper.find('[data-testid="enable-switch"]').exists()).toBe(false)
  })

  it('labels removal as archive for a provisioned action', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountAction({ automationId: 'auto-1' })
    await flushPromises()
    expect(wrapper.get('[data-testid="delete-node"]').text()).toBe('Archive')
  })

  it('labels removal as delete for an unprovisioned action', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountAction()
    await flushPromises()
    expect(wrapper.get('[data-testid="delete-node"]').text()).toBe('Delete')
  })

  it('hides the switch for an incomplete connected trigger', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    edges.value = [
      {
        id: 'edge',
        source: 'trigger',
        target: 'n1',
        data: { sourceKind: 'trigger' },
      },
    ]
    findNode.mockReturnValue({
      id: 'trigger',
      data: {
        trigger: {
          event_action: 'opened',
          repository_full_name: null,
        },
      },
    })
    const wrapper = mountAction({ name: 'Triage', playbookId: 'pb-1' })
    await flushPromises()
    expect(wrapper.find('[data-testid="enable-switch"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Trigger incomplete')
  })

  it('keeps whitespace-only names incomplete', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountAction({ name: '  ', playbookId: 'pb-1' })
    await flushPromises()
    expect(
      wrapper.get('[data-testid="canvas-node"]').attributes('data-incomplete'),
    ).toBe('true')
    expect(wrapper.text()).toContain('Incomplete')
    expect(wrapper.text()).toContain('Enter a name')
  })

  it('shows the playbook hint when only the name is set', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountAction({ name: 'Triage', playbookId: null })
    await flushPromises()
    expect(wrapper.text()).toContain('Choose a Playbook')
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

  it('hides the switch when the action is invalid', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountAction()
    await flushPromises()
    expect(wrapper.find('[data-testid="enable-switch"]').exists()).toBe(false)
  })

  it('enables a complete action and reports save failures', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const save = vi
      .fn()
      .mockResolvedValueOnce(true)
      .mockResolvedValueOnce(false)
    const wrapper = mountAction(
      {
        name: 'Triage',
        playbookId: 'pb-1',
        enabled: false,
      },
      save,
    )
    edges.value = [
      {
        id: 'edge',
        source: 'trigger',
        target: 'n1',
        data: { sourceKind: 'trigger' },
      },
    ]
    findNode.mockReturnValue({
      id: 'trigger',
      data: {
        trigger: {
          event_action: 'opened',
          repository_full_name: 'octo/repo',
        },
      },
    })
    await flushPromises()
    expect(wrapper.get('[data-testid="enable-switch"]').text()).toBe('Enable')
    await wrapper.get('[data-testid="enable-switch"]').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith('n1', { enabled: true })
    expect(wrapper.find('[data-testid="save-error"]').exists()).toBe(false)
    await wrapper.setProps({
      data: {
        name: 'Triage',
        playbookId: 'pb-1',
        enabled: true,
      },
    })
    await wrapper.get('[data-testid="enable-switch"]').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenLastCalledWith('n1', { enabled: false })
    expect(wrapper.find('[data-testid="save-error"]').exists()).toBe(true)
  })

  it('shows disable for an enabled invalid action', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountAction({
      name: 'Triage',
      playbookId: 'pb-1',
      enabled: true,
    })
    await flushPromises()
    expect(wrapper.get('[data-testid="enable-switch"]').text()).toBe('Disable')
  })

  it('shows sync status and error on the badge', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountAction({
      name: 'Triage',
      playbookId: 'pb-1',
      syncStatus: 'error',
      syncError: 'devin api returned HTTP 500',
    })
    await flushPromises()
    const badge = wrapper.get('[data-testid="sync-badge"]')
    expect(badge.text()).toBe('error')
    expect(badge.attributes('data-sync-status')).toBe('error')
    expect(badge.attributes('title')).toBe('devin api returned HTTP 500')
  })

  it('works without an injected saver', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountAction()
    await flushPromises()
    await wrapper.get('[data-testid="action-name"]').setValue('Updated')
    await expect(
      wrapper.get('[data-testid="action-name"]').trigger('change'),
    ).resolves.not.toThrow()
    await flushPromises()
    expect(wrapper.get('[data-testid="save-error"]').text()).toBe(
      'Could not save',
    )
  })

  it('shows and clears the save error', async () => {
    GET.mockResolvedValue({ data: [], error: undefined })
    const save = vi
      .fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true)
    const wrapper = mountAction({}, save)
    await flushPromises()
    const input = wrapper.get('[data-testid="action-name"]')
    ;(input.element as HTMLInputElement).value = 'First'
    await input.trigger('input')
    await input.trigger('change')
    await flushPromises()
    expect(save).toHaveBeenCalledWith('n1', { name: 'First' })
    expect(wrapper.get('[data-testid="save-error"]').text()).toBe(
      'Could not save',
    )
    ;(input.element as HTMLInputElement).value = 'Second'
    await input.trigger('input')
    await input.trigger('change')
    await flushPromises()
    expect(wrapper.find('[data-testid="save-error"]').exists()).toBe(false)
  })
})
