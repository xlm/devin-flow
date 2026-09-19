import { describe, expect, it } from 'vitest'
import {
  actionFieldsFromData,
  actionFieldsOf,
  actionInvalidReason,
  hasLinkedTrigger,
  isActionComplete,
} from '@/lib/actionValidity'

describe('action validity', () => {
  it('normalizes action data types', () => {
    expect(
      actionFieldsFromData({
        name: 'Triage',
        playbookId: 'pb-1',
        extraInstructions: 'Notes',
      }),
    ).toEqual({
      name: 'Triage',
      playbookId: 'pb-1',
      extraInstructions: 'Notes',
    })
    expect(
      actionFieldsFromData({
        name: 1,
        playbookId: false,
        extraInstructions: null,
      }),
    ).toEqual({
      name: '',
      playbookId: null,
      extraInstructions: '',
    })
  })

  it('maps action fields from the API shape', () => {
    expect(
      actionFieldsOf({
        id: 'n1',
        kind: 'action',
        position: { x: 1, y: 2 },
        name: 'Triage',
        playbook_id: 'pb-1',
        extra_instructions: 'Notes',
      }),
    ).toEqual({
      name: 'Triage',
      playbookId: 'pb-1',
      extraInstructions: 'Notes',
    })
  })

  it.each([
    [{ name: 'Triage', playbookId: 'pb-1' }, true],
    [{ name: ' ', playbookId: 'pb-1' }, false],
    [{ name: 'Triage', playbookId: null }, false],
  ])('checks action completion', (fields, complete) => {
    expect(isActionComplete(fields)).toBe(complete)
  })

  it('finds only linked trigger edges', () => {
    expect(
      hasLinkedTrigger('n1', [
        { target: 'n2', data: { sourceKind: 'trigger' } },
        { target: 'n1', data: { sourceKind: 'action' } },
      ]),
    ).toBe(false)
    expect(
      hasLinkedTrigger('n1', [
        { target: 'n1' },
        { target: 'n1', data: { sourceKind: 'trigger' } },
      ]),
    ).toBe(true)
  })

  it('prioritizes incomplete fields over a missing trigger', () => {
    expect(actionInvalidReason('n1', { name: '', playbookId: null }, [])).toBe(
      'incomplete',
    )
    expect(
      actionInvalidReason('n1', { name: 'Triage', playbookId: 'pb-1' }, []),
    ).toBe('no-trigger')
    expect(
      actionInvalidReason('n1', { name: 'Triage', playbookId: 'pb-1' }, [
        { target: 'n1', data: { sourceKind: 'trigger' } },
      ]),
    ).toBeNull()
  })
})
