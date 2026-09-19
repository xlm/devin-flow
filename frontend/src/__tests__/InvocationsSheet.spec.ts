import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

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

import InvocationsSheet from '@/components/InvocationsSheet.vue'

function mountSheet(props: Record<string, unknown> = {}) {
  return mount(InvocationsSheet, {
    props: {
      open: true,
      title: 'My invocations',
      description: 'Newest first',
      testId: 'probe',
      loading: false,
      loadError: false,
      empty: false,
      ...props,
    },
    slots: { default: () => h('div', { 'data-testid': 'rows' }, 'rows here') },
  })
}

describe('InvocationsSheet', () => {
  it('renders the title, description and slot content', () => {
    const wrapper = mountSheet()
    expect(wrapper.find('[data-testid="probe-sheet"]').exists()).toBe(true)
    expect(wrapper.find('h2').text()).toBe('My invocations')
    expect(wrapper.find('p').text()).toBe('Newest first')
    expect(wrapper.find('[data-testid="rows"]').text()).toBe('rows here')
    wrapper.unmount()
  })

  it('shows Loading while loading', () => {
    const wrapper = mountSheet({ loading: true })
    expect(wrapper.text()).toContain('Loading...')
    expect(wrapper.find('[data-testid="rows"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows the error block and emits retry', async () => {
    const wrapper = mountSheet({ loadError: true })
    expect(wrapper.find('[data-testid="probe-error"]').exists()).toBe(true)
    await wrapper.find('[data-testid="probe-retry"]').trigger('click')
    expect(wrapper.emitted('retry')).toEqual([[]])
    wrapper.unmount()
  })

  it('shows the empty message', () => {
    const wrapper = mountSheet({ empty: true })
    expect(wrapper.find('[data-testid="probe-empty"]').text()).toBe(
      'No invocations yet',
    )
    wrapper.unmount()
  })

  it('renders no content while closed', () => {
    const wrapper = mountSheet({ open: false })
    expect(wrapper.find('[data-testid="probe-sheet"]').exists()).toBe(true)
    expect(wrapper.find('h2').exists()).toBe(false)
    wrapper.unmount()
  })

  it('forwards update:open events', async () => {
    const wrapper = mountSheet()
    wrapper.findComponent({ name: 'SheetMock' }).vm.$emit('update:open', false)
    expect(wrapper.emitted('update:open')).toEqual([[false]])
    wrapper.unmount()
  })
})
