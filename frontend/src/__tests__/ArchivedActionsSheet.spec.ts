import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ARCHIVED_ACTION_MIME } from '@/lib/nodeKinds'

const mocks = vi.hoisted(() => ({
  GET: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  client: { GET: mocks.GET },
}))

vi.mock('@/components/ui/sheet', () => ({
  Sheet: defineComponent({
    name: 'SheetMock',
    props: {
      open: { type: Boolean, default: false },
      modal: { type: Boolean, default: true },
    },
    emits: ['update:open'],
    setup:
      (props, { slots, attrs }) =>
      () =>
        h(
          'div',
          {
            'data-testid': attrs['data-testid'],
            'data-modal': String(props.modal),
          },
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

import ArchivedActionsSheet from '@/components/ArchivedActionsSheet.vue'

function archived(overrides: Record<string, unknown> = {}) {
  return {
    id: 'action-1',
    kind: 'action',
    position: { x: 1, y: 2 },
    name: 'Triage',
    playbook_id: 'pb-triage',
    prompt: '',
    enabled: false,
    sync_status: 'disabled',
    sync_error: null,
    automation_id: 'auto-1',
    invocation_count: 3,
    archived_at: '2026-01-02T03:04:05Z',
    ...overrides,
  }
}

function mountSheet(props: { open?: boolean } = {}) {
  return mount(ArchivedActionsSheet, {
    props: { open: true, ...props },
  })
}

describe('ArchivedActionsSheet', () => {
  beforeEach(() => {
    mocks.GET.mockReset()
    mocks.GET.mockResolvedValue({ data: [archived()], error: undefined })
  })

  it('renders a non-modal sheet so rows can drop on the canvas', () => {
    const wrapper = mountSheet()
    expect(
      wrapper.find('[data-testid="archived-sheet"]').attributes('data-modal'),
    ).toBe('false')
    wrapper.unmount()
  })

  it('loads archived actions only once opened', async () => {
    const wrapper = mountSheet({ open: false })
    await flushPromises()
    expect(mocks.GET).not.toHaveBeenCalled()
    await wrapper.setProps({ open: true })
    await flushPromises()
    expect(mocks.GET).toHaveBeenCalledWith('/api/canvas/archived-actions')
    wrapper.unmount()
  })

  it('lists archived actions with their details', async () => {
    mocks.GET.mockResolvedValue({
      data: [
        archived(),
        archived({ id: 'a-2', name: '  ', playbook_id: null }),
      ],
      error: undefined,
    })
    const wrapper = mountSheet()
    await flushPromises()
    const rows = wrapper.findAll('[data-testid="archived-action"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('Triage')
    expect(rows[0].text()).toContain('pb-triage')
    expect(rows[0].text()).toContain('3 invocations')
    expect(rows[1].text()).toContain('Untitled action')
    expect(rows[1].text()).toContain('No playbook')
    wrapper.unmount()
  })

  it('emits restore when the Restore button is clicked', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    await wrapper.find('[data-testid="archived-restore"]').trigger('click')
    expect(wrapper.emitted('restore')).toEqual([['action-1']])
    wrapper.unmount()
  })

  it('writes the action id to the drag payload', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    const dataTransfer = { setData: vi.fn(), effectAllowed: '' }
    await wrapper
      .find('[data-testid="archived-action"]')
      .trigger('dragstart', { dataTransfer })
    expect(dataTransfer.setData).toHaveBeenCalledWith(
      ARCHIVED_ACTION_MIME,
      'action-1',
    )
    expect(dataTransfer.effectAllowed).toBe('move')
    wrapper.unmount()
  })

  it('forwards close events and tolerates drags without dataTransfer', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    wrapper.findComponent({ name: 'SheetMock' }).vm.$emit('update:open', false)
    expect(wrapper.emitted('update:open')).toEqual([[false]])
    await expect(
      wrapper.find('[data-testid="archived-action"]').trigger('dragstart'),
    ).resolves.not.toThrow()
    wrapper.unmount()
  })

  it('removes a restored row locally', async () => {
    const wrapper = mountSheet()
    await flushPromises()
    expect(wrapper.findAll('[data-testid="archived-action"]')).toHaveLength(1)
    ;(wrapper.vm as unknown as { remove: (id: string) => void }).remove(
      'action-1',
    )
    await flushPromises()
    expect(wrapper.find('[data-testid="archived-empty"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows an empty state', async () => {
    mocks.GET.mockResolvedValue({ data: [], error: undefined })
    const wrapper = mountSheet()
    await flushPromises()
    expect(wrapper.find('[data-testid="archived-empty"]').text()).toBe(
      'No archived actions',
    )
    wrapper.unmount()
  })

  it('shows an error state and retries', async () => {
    mocks.GET.mockRejectedValueOnce(new Error('down'))
    const wrapper = mountSheet()
    await flushPromises()
    expect(wrapper.find('[data-testid="archived-error"]').exists()).toBe(true)
    mocks.GET.mockResolvedValue({ data: [archived()], error: undefined })
    await wrapper.find('[data-testid="archived-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="archived-action"]')).toHaveLength(1)
    wrapper.unmount()
  })
})
