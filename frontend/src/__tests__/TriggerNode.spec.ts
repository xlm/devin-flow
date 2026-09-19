import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  GET: vi.fn(),
  PATCH: vi.fn(),
  removeNodes: vi.fn(),
  updateNodeData: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  client: { GET: mocks.GET, PATCH: mocks.PATCH },
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

import TriggerNode from '@/components/nodes/TriggerNode.vue'
import type { TriggerRead } from '@/lib/connectRules'

const emptyTrigger: TriggerRead = {
  event_action: null,
  repository_full_name: null,
}

function mountNode(trigger = emptyTrigger) {
  const wrapper = mount(TriggerNode, {
    props: {
      id: 'node-1',
      data: { kind: 'trigger', label: 'Trigger', trigger },
    } as never,
  })
  mocks.updateNodeData.mockImplementation(
    (_id: string, update: { trigger: TriggerRead }) => {
      void wrapper.setProps({
        data: {
          ...(wrapper.props('data') as {
            kind: 'trigger'
            label: string
            trigger?: TriggerRead
          }),
          ...update,
        },
      })
    },
  )
  return wrapper
}

function repositoryResponse(repo = 'octo/repo') {
  return {
    data: [{ repo_path: repo, repo_name: repo.split('/')[1] }],
    error: undefined,
  }
}

function savedResponse(trigger = emptyTrigger) {
  return {
    data: {
      id: 'node-1',
      kind: 'trigger',
      position: { x: 1, y: 2 },
      trigger,
    },
    error: undefined,
  }
}

describe('TriggerNode', () => {
  beforeEach(() => {
    mocks.GET.mockReset()
    mocks.PATCH.mockReset()
    mocks.removeNodes.mockReset()
    mocks.updateNodeData.mockReset()
    mocks.GET.mockResolvedValue(repositoryResponse())
    mocks.PATCH.mockResolvedValue(savedResponse())
  })

  it('renders incomplete with empty trigger data', async () => {
    const wrapper = mountNode()
    await flushPromises()
    expect(
      wrapper.find('[data-testid="canvas-node"]').attributes('data-incomplete'),
    ).toBe('true')
    expect(wrapper.text()).toContain('Incomplete')
    wrapper.unmount()
  })

  it('renders complete when event and repository are set', async () => {
    const wrapper = mountNode({
      event_action: 'opened',
      repository_full_name: 'octo/repo',
    })
    await flushPromises()
    expect(
      wrapper.find('[data-testid="canvas-node"]').attributes('data-incomplete'),
    ).toBe('false')
    expect(wrapper.text()).toContain('Ready')
    wrapper.unmount()
  })

  it('lists repositories and saves a selected repository', async () => {
    const wrapper = mountNode()
    await flushPromises()
    await wrapper
      .find('[data-testid="trigger-repository"]')
      .setValue('octo/repo')
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      expect.objectContaining({
        body: { trigger: { repository_full_name: 'octo/repo' } },
      }),
    )
    expect(mocks.updateNodeData).toHaveBeenCalledWith('node-1', {
      trigger: emptyTrigger,
    })
    wrapper.unmount()
  })

  it('saves null when select fields are cleared', async () => {
    const wrapper = mountNode({
      event_action: 'opened',
      repository_full_name: 'octo/repo',
    })
    await flushPromises()
    await wrapper.find('[data-testid="trigger-event"]').setValue('')
    await wrapper.find('[data-testid="trigger-repository"]').setValue('')
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      expect.objectContaining({ body: { trigger: { event_action: null } } }),
    )
    expect(mocks.PATCH).toHaveBeenLastCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      expect.objectContaining({
        body: { trigger: { repository_full_name: null } },
      }),
    )
    wrapper.unmount()
  })

  it('shows no eligible repositories when the list is empty', async () => {
    mocks.GET.mockResolvedValueOnce({ data: [], error: undefined })
    const wrapper = mountNode()
    await flushPromises()
    expect(wrapper.find('[data-testid="trigger-repository"]').exists()).toBe(
      true,
    )
    expect(wrapper.text()).toContain('No eligible repositories')
    wrapper.unmount()
  })

  it.each([{ result: { error: { detail: 'failed' } } }, { throws: true }])(
    'shows repository loading errors (%s)',
    async (failure) => {
      if (failure.throws) mocks.GET.mockRejectedValueOnce(new Error('down'))
      else mocks.GET.mockResolvedValueOnce(failure.result)
      const wrapper = mountNode()
      await flushPromises()
      expect(wrapper.find('[data-testid="trigger-repository"]').exists()).toBe(
        true,
      )
      expect(wrapper.text()).toContain('Could not load repositories')
      expect(
        wrapper.find('[data-testid="trigger-repositories-retry"]').exists(),
      ).toBe(true)
      wrapper.unmount()
    },
  )

  it('retries repository loading and switches back to a select', async () => {
    mocks.GET.mockResolvedValueOnce({ error: { detail: 'failed' } })
    mocks.GET.mockResolvedValueOnce(repositoryResponse('octo/retry'))
    const wrapper = mountNode()
    await flushPromises()
    await wrapper
      .find('[data-testid="trigger-repositories-retry"]')
      .trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="trigger-repository"]').exists()).toBe(
      true,
    )
    wrapper.unmount()
  })

  it('does not show a repository availability hint when repositories exist', async () => {
    const wrapper = mountNode()
    await flushPromises()
    expect(wrapper.text()).not.toContain('Could not load repositories')
    expect(wrapper.text()).not.toContain('No eligible repositories')
    wrapper.unmount()
  })

  it('saves event changes', async () => {
    const wrapper = mountNode()
    await flushPromises()
    await wrapper.find('[data-testid="trigger-event"]').setValue('closed')
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      expect.objectContaining({
        body: { trigger: { event_action: 'closed' } },
      }),
    )
    wrapper.unmount()
  })

  it('clears a saved event', async () => {
    const wrapper = mountNode({
      event_action: 'opened',
      repository_full_name: 'octo/repo',
    })
    await flushPromises()
    await wrapper.find('[data-testid="trigger-event"]').setValue('')
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledWith(
      '/api/canvas/nodes/{kind}/{node_id}',
      expect.objectContaining({
        body: { trigger: { event_action: null } },
      }),
    )
    wrapper.unmount()
  })

  it.each([false, true])(
    'rolls back and reports save failures (%s)',
    async (throws) => {
      mocks.PATCH.mockImplementationOnce(() =>
        throws
          ? Promise.reject(new Error('down'))
          : Promise.resolve({ error: { detail: 'failed' } }),
      )
      const wrapper = mountNode({
        event_action: 'opened',
        repository_full_name: 'octo/repo',
      })
      await flushPromises()
      const select = wrapper.find('[data-testid="trigger-event"]')
      await select.setValue('closed')
      await flushPromises()
      expect((select.element as HTMLSelectElement).value).toBe('opened')
      expect(wrapper.find('[role="alert"]').text()).toBe('Could not save')
      wrapper.unmount()
    },
  )

  it('keeps a saved repository that is absent from the list', async () => {
    const wrapper = mountNode({
      event_action: null,
      repository_full_name: 'octo/saved',
    })
    await flushPromises()
    expect(
      wrapper
        .find('[data-testid="trigger-repository"] option[value="octo/saved"]')
        .exists(),
    ).toBe(true)
    wrapper.unmount()
  })

  it('serializes concurrent saves for one node', async () => {
    let resolveFirst:
      ((value: ReturnType<typeof savedResponse>) => void) | undefined
    mocks.PATCH.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve
        }),
    )
    const wrapper = mountNode()
    await flushPromises()
    await wrapper.find('[data-testid="trigger-event"]').setValue('opened')
    await wrapper
      .find('[data-testid="trigger-repository"]')
      .setValue('octo/repo')
    expect(mocks.PATCH).toHaveBeenCalledTimes(1)
    resolveFirst?.(savedResponse())
    await flushPromises()
    expect(mocks.PATCH).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('rolls back a queued failure to the latest confirmed state', async () => {
    let resolveFirst:
      ((value: ReturnType<typeof savedResponse>) => void) | undefined
    mocks.PATCH.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve
        }),
    )
    mocks.PATCH.mockImplementationOnce(() => Promise.reject(new Error('down')))
    const wrapper = mountNode({
      event_action: 'opened',
      repository_full_name: 'octo/one',
    })
    await flushPromises()
    await wrapper.find('[data-testid="trigger-event"]').setValue('closed')
    await wrapper
      .find('[data-testid="trigger-repository"]')
      .setValue('octo/two')
    resolveFirst?.(
      savedResponse({
        event_action: 'closed',
        repository_full_name: 'octo/one',
      }),
    )
    await flushPromises()
    expect(
      (
        wrapper.find('[data-testid="trigger-event"]')
          .element as HTMLSelectElement
      ).value,
    ).toBe('closed')
    expect(
      (
        wrapper.find('[data-testid="trigger-repository"]')
          .element as HTMLSelectElement
      ).value,
    ).toBe('octo/one')
    expect(wrapper.find('[role="alert"]').text()).toBe('Could not save')
    wrapper.unmount()
  })
})
