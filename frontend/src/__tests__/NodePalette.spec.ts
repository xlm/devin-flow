import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import NodePalette from '@/components/NodePalette.vue'
import { NODE_KIND_MIME } from '@/lib/nodeKinds'

describe('NodePalette', () => {
  it('renders node entries in palette order', () => {
    const wrapper = mount(NodePalette)
    expect(
      wrapper
        .findAll('[role="listitem"]')
        .map((entry) => entry.text().replace(/\s+/g, ' ').trim()),
    ).toEqual([
      'TriggerChoose repository and event',
      'ActionChoose a Playbook',
      'OutcomeChoose an Outcome kind',
    ])
  })

  it('writes the node kind to the drag payload', async () => {
    const wrapper = mount(NodePalette)
    const dataTransfer = {
      setData: vi.fn(),
      effectAllowed: '',
    }
    await wrapper
      .find('[data-testid="palette-action"]')
      .trigger('dragstart', { dataTransfer })
    expect(dataTransfer.setData).toHaveBeenCalledWith(NODE_KIND_MIME, 'action')
    expect(dataTransfer.effectAllowed).toBe('move')
  })

  it('allows dragstart without a data transfer object', async () => {
    const wrapper = mount(NodePalette)
    await expect(
      wrapper.find('[data-testid="palette-trigger"]').trigger('dragstart'),
    ).resolves.not.toThrow()
  })

  it('disables entries while the canvas is loading', () => {
    const wrapper = mount(NodePalette, { props: { disabled: true } })
    const entry = wrapper.find('[data-testid="palette-trigger"]')
    expect(entry.attributes('draggable')).toBe('false')
    expect(entry.attributes('aria-disabled')).toBe('true')
    expect(entry.classes()).toContain('cursor-not-allowed')
    expect(entry.classes()).toContain('opacity-50')
  })
})
