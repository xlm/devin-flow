import { describe, expect, it } from 'vitest'
import {
  actionFieldsFromData,
  actionFieldsOf,
  actionIncompleteHint,
  actionInvalidReason,
  hasLinkedTrigger,
  isActionComplete,
  syncStateFromData,
} from '@/lib/actionValidity'

describe('action validity', () => {
  it('normalizes action data types', () => {
    expect(
      actionFieldsFromData({
        name: 'Triage',
        playbookId: 'pb-1',
        prompt: 'Notes',
      }),
    ).toEqual({
      name: 'Triage',
      playbookId: 'pb-1',
      prompt: 'Notes',
      enabled: false,
    })
    expect(
      actionFieldsFromData({
        name: 1,
        playbookId: false,
        prompt: null,
      }),
    ).toEqual({
      name: '',
      playbookId: null,
      prompt: '',
      enabled: false,
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
        prompt: 'Notes',
        enabled: true,
        sync_status: 'enabled',
        sync_error: null,
        automation_id: null,
      }),
    ).toEqual({
      name: 'Triage',
      playbookId: 'pb-1',
      prompt: 'Notes',
      enabled: true,
    })
  })

  it('normalizes sync state', () => {
    expect(
      syncStateFromData({ syncStatus: 'error', syncError: 'failed' }),
    ).toEqual({ status: 'error', error: 'failed' })
    expect(syncStateFromData({})).toEqual({
      status: 'unprovisioned',
      error: null,
    })
  })

  it.each([
    [{ name: 'Triage', playbookId: 'pb-1' }, true],
    [{ name: ' ', playbookId: 'pb-1' }, false],
    [{ name: 'Triage', playbookId: null }, false],
  ])('checks action completion', (fields, complete) => {
    expect(isActionComplete(fields)).toBe(complete)
  })

  it.each([
    [{ name: '', playbookId: null }, 'Enter a name and choose a Playbook'],
    [{ name: '', playbookId: 'pb-1' }, 'Enter a name'],
    [{ name: 'Triage', playbookId: null }, 'Choose a Playbook'],
    [{ name: 'Triage', playbookId: 'pb-1' }, null],
  ])('describes incomplete action fields', (fields, hint) => {
    expect(actionIncompleteHint(fields)).toBe(hint)
  })

  it('finds only linked trigger edges', () => {
    expect(
      hasLinkedTrigger('n1', [
        { source: 'trigger', target: 'n2', data: { sourceKind: 'trigger' } },
        { source: 'action', target: 'n1', data: { sourceKind: 'action' } },
      ]),
    ).toBe(false)
    expect(
      hasLinkedTrigger('n1', [
        { source: 'action', target: 'n1' },
        { source: 'trigger', target: 'n1', data: { sourceKind: 'trigger' } },
      ]),
    ).toBe(true)
  })

  it('prioritizes incomplete fields over a missing trigger', () => {
    expect(
      actionInvalidReason(
        'n1',
        { name: '', playbookId: null },
        [],
        () => undefined,
      ),
    ).toBe('incomplete')
    expect(
      actionInvalidReason(
        'n1',
        { name: 'Triage', playbookId: 'pb-1' },
        [],
        () => undefined,
      ),
    ).toBe('no-trigger')
    expect(
      actionInvalidReason(
        'n1',
        { name: 'Triage', playbookId: 'pb-1' },
        [{ source: 'trigger', target: 'n1', data: { sourceKind: 'trigger' } }],
        () => ({
          trigger: {
            event_action: 'opened',
            repository_full_name: 'octo/repo',
          },
        }),
      ),
    ).toBeNull()
    expect(
      actionInvalidReason(
        'n1',
        { name: 'Triage', playbookId: 'pb-1' },
        [{ source: 'trigger', target: 'n1', data: { sourceKind: 'trigger' } }],
        () => ({
          trigger: {
            event_action: 'opened',
            repository_full_name: null,
          },
        }),
      ),
    ).toBe('trigger-incomplete')
  })
})
