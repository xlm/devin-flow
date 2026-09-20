import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  client: { GET: mocks.GET, POST: mocks.POST },
}))

vi.mock('@/components/ui/sheet', () => ({
  Sheet: defineComponent({
    name: 'SheetMock',
    props: { open: { type: Boolean, default: false } },
    emits: ['update:open'],
    setup:
      (props, { slots }) =>
      () =>
        h(
          'div',
          { 'data-testid': 'outcome-sheet' },
          props.open ? slots.default?.() : [],
        ),
  }),
  SheetContent: defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.()),
  }),
  SheetHeader: defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.()),
  }),
  SheetTitle: defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('h2', slots.default?.()),
  }),
  SheetDescription: defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('p', slots.default?.()),
  }),
}))

import OutcomeInvocationsSheet from '@/components/OutcomeInvocationsSheet.vue'
import type { OutcomeKind } from '@/lib/connectRules'

function invocation(overrides: Record<string, unknown> = {}) {
  return {
    id: 'inv-1',
    session_id: 's-1',
    title: 'Triage session',
    url: 'https://app.devin.ai/sessions/s-1',
    status: 'exit',
    session_created_at: '2026-01-02T03:04:05Z',
    archived_at: null,
    pull_requests: [{ url: 'https://github.com/a/b/pull/1', state: 'merged' }],
    duplicate_of: null,
    ...overrides,
  }
}

function mountSheet(props: {
  open?: boolean
  nodeId?: string | null
  actionNodeId?: string | null
  kind?: OutcomeKind | null
}) {
  return mount(OutcomeInvocationsSheet, {
    props: {
      open: true,
      nodeId: 'node-1',
      actionNodeId: null,
      kind: 'duplicate',
      ...props,
    },
  })
}

describe('OutcomeInvocationsSheet', () => {
  beforeEach(() => {
    mocks.GET.mockReset()
    mocks.POST.mockReset()
    mocks.GET.mockResolvedValue({ data: [invocation()], error: undefined })
  })

  it('shows a loading state while fetching', async () => {
    mocks.GET.mockReturnValue(new Promise(() => {}))
    const wrapper = mountSheet({})
    await flushPromises()
    expect(wrapper.text()).toContain('Loading...')
    wrapper.unmount()
  })

  it('lists invocations with links and PR state badges', async () => {
    const wrapper = mountSheet({})
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledWith(
      '/api/outcome-nodes/{node_id}/invocations',
      { params: { path: { node_id: 'node-1' }, query: {} } },
    )
    const item = wrapper.find('[data-testid="outcome-invocation"]')
    expect(item.text()).toContain('Triage session')
    expect(item.text()).toContain('exit')
    const links = item.findAll('a')
    expect(
      links.some(
        (link) =>
          link.attributes('href') === 'https://app.devin.ai/sessions/s-1',
      ),
    ).toBe(true)
    const prLink = links.find(
      (link) => link.attributes('href') === 'https://github.com/a/b/pull/1',
    )
    expect(prLink?.text()).toContain('pull/1')
    expect(item.text()).toContain('merged')
    wrapper.unmount()
  })

  it('sends the action node id as a query param', async () => {
    const wrapper = mountSheet({ actionNodeId: 'action-1' })
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledWith(
      '/api/outcome-nodes/{node_id}/invocations',
      {
        params: {
          path: { node_id: 'node-1' },
          query: { action_node_id: 'action-1' },
        },
      },
    )
    wrapper.unmount()
  })

  it('refetches when the action node id changes', async () => {
    const wrapper = mountSheet({})
    await flushPromises()
    await wrapper.setProps({ actionNodeId: 'action-1' })
    await flushPromises()
    expect(mocks.GET).toHaveBeenLastCalledWith(
      '/api/outcome-nodes/{node_id}/invocations',
      {
        params: {
          path: { node_id: 'node-1' },
          query: { action_node_id: 'action-1' },
        },
      },
    )
    wrapper.unmount()
  })

  it('falls back to session id and renders duplicate links', async () => {
    mocks.GET.mockResolvedValue({
      data: [
        invocation({
          title: null,
          url: null,
          pull_requests: [],
          duplicate_of: 'https://app.devin.ai/sessions/s-0',
        }),
      ],
      error: undefined,
    })
    const wrapper = mountSheet({})
    await flushPromises()
    const item = wrapper.find('[data-testid="outcome-invocation"]')
    expect(item.text()).toContain('s-1')
    expect(item.find('a').attributes('href')).toBe(
      'https://app.devin.ai/sessions/s-0',
    )
    expect(item.text()).toContain('Duplicate of')
    wrapper.unmount()
  })

  it('colors the status dot by session status', async () => {
    mocks.GET.mockResolvedValue({
      data: [
        invocation({ id: 'inv-1', status: 'running' }),
        invocation({ id: 'inv-2', status: 'error' }),
      ],
      error: undefined,
    })
    const wrapper = mountSheet({})
    await flushPromises()
    const items = wrapper.findAll('[data-testid="outcome-invocation"]')
    expect(items).toHaveLength(2)
    const dots = items.map((item) =>
      item.find('[data-testid="session-status-dot"]'),
    )
    expect(dots[0].classes()).toContain('bg-amber-500')
    expect(dots[1].classes()).toContain('bg-destructive')
    expect(items[0].text()).toContain('running')
    expect(items[1].text()).toContain('error')
    wrapper.unmount()
  })

  it('shows the empty state', async () => {
    mocks.GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountSheet({})
    await flushPromises()
    expect(wrapper.find('[data-testid="outcome-empty"]').text()).toBe(
      'No invocations yet',
    )
    wrapper.unmount()
  })

  it('shows an error and retries', async () => {
    mocks.GET.mockResolvedValueOnce({ data: undefined, error: { detail: 'x' } })
    const wrapper = mountSheet({})
    await flushPromises()
    expect(wrapper.find('[data-testid="outcome-error"]').exists()).toBe(true)
    await wrapper.find('[data-testid="outcome-retry"]').trigger('click')
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-testid="outcome-invocation"]').exists()).toBe(
      true,
    )
    wrapper.unmount()
  })

  it('shows an error when the request throws', async () => {
    mocks.GET.mockRejectedValue(new Error('down'))
    const wrapper = mountSheet({})
    await flushPromises()
    expect(wrapper.find('[data-testid="outcome-error"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('archives an invocation and emits success', async () => {
    mocks.GET.mockResolvedValueOnce({ data: [invocation()], error: undefined })
    mocks.GET.mockResolvedValueOnce({ data: [], error: undefined })
    mocks.POST.mockResolvedValue({ data: undefined, error: undefined })
    const wrapper = mountSheet({})
    await flushPromises()
    await wrapper.find('[data-testid="archive-invocation"]').trigger('click')
    await flushPromises()
    expect(mocks.POST).toHaveBeenCalledWith(
      '/api/invocations/{invocation_id}/archive',
      { params: { path: { invocation_id: 'inv-1' } } },
    )
    expect(wrapper.emitted('archived')).toEqual([[]])
    wrapper.unmount()
  })

  it('shows an archive error when archiving fails', async () => {
    mocks.POST.mockResolvedValue({ data: undefined, error: { detail: 'down' } })
    const wrapper = mountSheet({})
    await flushPromises()
    await wrapper.find('[data-testid="archive-invocation"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="archive-error"]').text()).toBe(
      'Could not archive session',
    )
    expect(wrapper.emitted('archived')).toBeUndefined()
    wrapper.unmount()
  })

  it('renders archived invocations with a disabled Archived button', async () => {
    mocks.GET.mockResolvedValue({
      data: [invocation({ archived_at: '2026-01-03T03:04:05Z' })],
      error: undefined,
    })
    const wrapper = mountSheet({})
    await flushPromises()
    const button = wrapper.find('[data-testid="archive-invocation"]')
    expect(button.text()).toBe('Archived')
    expect(button.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('keeps the row and marks it archived after a successful archive', async () => {
    mocks.GET.mockResolvedValueOnce({
      data: [invocation()],
      error: undefined,
    })
    mocks.GET.mockResolvedValueOnce({
      data: [invocation({ archived_at: '2026-01-03T03:04:05Z' })],
      error: undefined,
    })
    mocks.POST.mockResolvedValue({ data: undefined, error: undefined })
    const wrapper = mountSheet({})
    await flushPromises()
    await wrapper.find('[data-testid="archive-invocation"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="outcome-invocation"]')).toHaveLength(
      1,
    )
    const button = wrapper.find('[data-testid="archive-invocation"]')
    expect(button.text()).toBe('Archived')
    expect(button.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('does not fetch without a node id', async () => {
    const wrapper = mountSheet({ nodeId: null })
    await flushPromises()
    expect(mocks.GET).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('does not render content while closed and refetches on reopen', async () => {
    const wrapper = mountSheet({ open: false })
    await flushPromises()
    expect(mocks.GET).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="outcome-invocation"]').exists()).toBe(
      false,
    )
    await wrapper.setProps({ open: true })
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(1)
    await wrapper.setProps({ open: false })
    await wrapper.setProps({ open: true })
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('ignores a stale response resolving after a newer load', async () => {
    let resolveA: ((value: { data: unknown[] }) => void) | undefined
    let resolveB: ((value: { data: unknown[] }) => void) | undefined
    mocks.GET.mockImplementationOnce(
      () => new Promise((resolve) => (resolveA = resolve)),
    ).mockImplementationOnce(
      () => new Promise((resolve) => (resolveB = resolve)),
    )
    const wrapper = mountSheet({ nodeId: 'node-a' })
    await flushPromises()
    await wrapper.setProps({ nodeId: 'node-b' })
    await flushPromises()
    resolveB?.({ data: [invocation({ session_id: 's-b', title: 'B row' })] })
    await flushPromises()
    resolveA?.({ data: [invocation({ session_id: 's-a', title: 'A row' })] })
    await flushPromises()
    const items = wrapper.findAll('[data-testid="outcome-invocation"]')
    expect(items).toHaveLength(1)
    expect(items[0].text()).toContain('B row')
    expect(wrapper.text()).not.toContain('A row')
    expect(wrapper.text()).not.toContain('Loading...')
    expect(wrapper.find('[data-testid="outcome-error"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('ignores a stale failure resolving after a newer load', async () => {
    let rejectA: ((reason: unknown) => void) | undefined
    let resolveB: ((value: { data: unknown[] }) => void) | undefined
    mocks.GET.mockImplementationOnce(
      () => new Promise((_, reject) => (rejectA = reject)),
    ).mockImplementationOnce(
      () => new Promise((resolve) => (resolveB = resolve)),
    )
    const wrapper = mountSheet({ nodeId: 'node-a' })
    await flushPromises()
    await wrapper.setProps({ nodeId: 'node-b' })
    await flushPromises()
    resolveB?.({ data: [invocation({ session_id: 's-b', title: 'B row' })] })
    await flushPromises()
    rejectA?.(new Error('down'))
    await flushPromises()
    expect(wrapper.find('[data-testid="outcome-error"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="outcome-invocation"]')).toHaveLength(
      1,
    )
    wrapper.unmount()
  })

  it('forwards update:open events', async () => {
    const wrapper = mountSheet({})
    await flushPromises()
    wrapper.findComponent({ name: 'SheetMock' }).vm.$emit('update:open', false)
    await flushPromises()
    expect(wrapper.emitted('update:open')).toEqual([[false]])
    wrapper.unmount()
  })

  it('uses a generic title when the kind is unset', async () => {
    const wrapper = mountSheet({ kind: null })
    await flushPromises()
    expect(wrapper.find('h2').text()).toBe('Outcome')
    wrapper.unmount()
  })

  it('labels the title with the outcome kind', async () => {
    const wrapper = mountSheet({ kind: 'not_reproducible' })
    await flushPromises()
    expect(wrapper.find('h2').text()).toBe('Not reproducible outcomes')
    wrapper.unmount()
  })
})
