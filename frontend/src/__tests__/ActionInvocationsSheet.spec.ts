import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  GET: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  client: { GET: mocks.GET },
}))

vi.mock('@/components/ui/sheet', () => ({
  Sheet: defineComponent({
    name: 'SheetMock',
    props: { open: { type: Boolean, default: false } },
    emits: ['update:open'],
    setup:
      (props, { slots, attrs }) =>
      () =>
        h(
          'div',
          { 'data-testid': attrs['data-testid'] },
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

import ActionInvocationsSheet from '@/components/ActionInvocationsSheet.vue'

function invocation(overrides: Record<string, unknown> = {}) {
  return {
    id: 'inv-1',
    session_id: 's-1',
    title: 'Triage session',
    url: 'https://app.devin.ai/sessions/s-1',
    status: 'exit',
    session_created_at: '2026-01-02T03:04:05Z',
    pull_requests: [],
    duplicate_of: null,
    issue: null,
    ...overrides,
  }
}

function mountSheet(props: {
  open?: boolean
  nodeId?: string | null
  actionName?: string | null
}) {
  return mount(ActionInvocationsSheet, {
    props: {
      open: true,
      nodeId: 'node-1',
      actionName: 'Triage',
      ...props,
    },
  })
}

describe('ActionInvocationsSheet', () => {
  beforeEach(() => {
    mocks.GET.mockReset()
    mocks.GET.mockResolvedValue({ data: [invocation()], error: undefined })
  })

  it('shows a loading state while fetching', async () => {
    mocks.GET.mockReturnValue(new Promise(() => {}))
    const wrapper = mountSheet({})
    await flushPromises()
    expect(wrapper.text()).toContain('Loading...')
    wrapper.unmount()
  })

  it('lists invocations with session links', async () => {
    const wrapper = mountSheet({})
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledWith(
      '/api/action-nodes/{node_id}/invocations',
      { params: { path: { node_id: 'node-1' } } },
    )
    expect(wrapper.find('h2').text()).toBe('Triage invocations')
    const item = wrapper.find('[data-testid="action-invocation"]')
    expect(item.text()).toContain('Triage session')
    expect(item.text()).toContain('exit')
    expect(item.text()).toContain('Issue unknown')
    const sessionLink = item
      .findAll('a')
      .find((link) => link.text() === 'Session')
    expect(sessionLink?.attributes('href')).toBe(
      'https://app.devin.ai/sessions/s-1',
    )
    wrapper.unmount()
  })

  it('renders the issue number and title as a link', async () => {
    mocks.GET.mockResolvedValue({
      data: [
        invocation({
          issue: {
            url: 'https://github.com/a/b/issues/9',
            number: 9,
            title: 'Boom',
          },
          pull_requests: [
            { url: 'https://github.com/a/b/pull/2', state: 'open' },
          ],
        }),
      ],
      error: undefined,
    })
    const wrapper = mountSheet({})
    await flushPromises()
    const item = wrapper.find('[data-testid="action-invocation"]')
    const issueLink = item.find('a')
    expect(issueLink.attributes('href')).toBe('https://github.com/a/b/issues/9')
    expect(issueLink.text()).toBe('#9 Boom')
    expect(item.text()).toContain('open')
    wrapper.unmount()
  })

  it('falls back to the issue url when number and title are null', async () => {
    mocks.GET.mockResolvedValue({
      data: [
        invocation({
          issue: {
            url: 'https://github.com/a/b/issues/9',
            number: null,
            title: null,
          },
        }),
      ],
      error: undefined,
    })
    const wrapper = mountSheet({})
    await flushPromises()
    const link = wrapper.find('[data-testid="action-invocation"] a')
    expect(link.text()).toBe('https://github.com/a/b/issues/9')
    wrapper.unmount()
  })

  it('uses a generic title and session id fallbacks', async () => {
    mocks.GET.mockResolvedValue({
      data: [invocation({ title: null, url: null })],
      error: undefined,
    })
    const wrapper = mountSheet({ actionName: null })
    await flushPromises()
    expect(wrapper.find('h2').text()).toBe('Action invocations')
    wrapper.unmount()
  })

  it('falls back to the generic title for an empty action name', async () => {
    const wrapper = mountSheet({ actionName: '' })
    await flushPromises()
    expect(wrapper.find('h2').text()).toBe('Action invocations')
    const item = wrapper.find('[data-testid="action-invocation"]')
    expect(item.text()).toContain('Triage session')
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
    const items = wrapper.findAll('[data-testid="action-invocation"]')
    expect(items).toHaveLength(2)
    const dots = items.map((item) =>
      item.find('[data-testid="session-status-dot"]'),
    )
    expect(dots[0].classes()).toContain('bg-blue-500')
    expect(dots[1].classes()).toContain('bg-destructive')
    expect(items[0].text()).toContain('running')
    expect(items[1].text()).toContain('error')
    wrapper.unmount()
  })

  it('shows the empty state', async () => {
    mocks.GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountSheet({})
    await flushPromises()
    expect(wrapper.find('[data-testid="action-empty"]').text()).toBe(
      'No invocations yet',
    )
    wrapper.unmount()
  })

  it('shows an error and retries', async () => {
    mocks.GET.mockResolvedValueOnce({ data: undefined, error: { detail: 'x' } })
    const wrapper = mountSheet({})
    await flushPromises()
    expect(wrapper.find('[data-testid="action-error"]').exists()).toBe(true)
    await wrapper.find('[data-testid="action-retry"]').trigger('click')
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-testid="action-invocation"]').exists()).toBe(
      true,
    )
    wrapper.unmount()
  })

  it('ignores a stale response resolving after a newer load', async () => {
    let resolveA: ((value: { data: unknown[] }) => void) | undefined
    let resolveB: ((value: { data: unknown[] }) => void) | undefined
    mocks.GET.mockImplementationOnce(
      () => new Promise((resolve) => (resolveA = resolve)),
    )
    mocks.GET.mockImplementationOnce(
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
    const items = wrapper.findAll('[data-testid="action-invocation"]')
    expect(items).toHaveLength(1)
    expect(items[0].text()).toContain('B row')
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

  it('does not fetch while closed or without a node id', async () => {
    const closed = mountSheet({ open: false })
    await flushPromises()
    expect(mocks.GET).not.toHaveBeenCalled()
    closed.unmount()
    const noNode = mountSheet({ nodeId: null })
    await flushPromises()
    expect(mocks.GET).not.toHaveBeenCalled()
    noNode.unmount()
  })
})
