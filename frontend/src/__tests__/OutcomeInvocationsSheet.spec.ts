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
    pull_requests: [{ url: 'https://github.com/a/b/pull/1', state: 'merged' }],
    duplicate_of: null,
    ...overrides,
  }
}

function mountSheet(props: {
  open?: boolean
  nodeId?: string | null
  kind?: OutcomeKind | null
}) {
  return mount(OutcomeInvocationsSheet, {
    props: { open: true, nodeId: 'node-1', kind: 'duplicate', ...props },
  })
}

describe('OutcomeInvocationsSheet', () => {
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

  it('lists invocations with links and PR state badges', async () => {
    const wrapper = mountSheet({})
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledWith(
      '/api/outcome-nodes/{node_id}/invocations',
      { params: { path: { node_id: 'node-1' } } },
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
