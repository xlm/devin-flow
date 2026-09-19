import { describe, expect, it } from 'vitest'
import { connectError, kindOf, type NodeKind } from '@/lib/connectRules'

const kinds: NodeKind[] = ['trigger', 'action', 'outcome']
const validPairs = new Set(['trigger:action', 'action:outcome'])

function node(
  kind: NodeKind,
  id: string = kind,
): { id: string; kind: NodeKind } {
  return { id, kind }
}

describe('connectError', () => {
  it('checks every node kind pair', () => {
    for (const sourceKind of kinds) {
      for (const targetKind of kinds) {
        const result = connectError(
          node(sourceKind, 'source'),
          node(targetKind, 'target'),
          [],
        )
        expect(result).toBe(
          validPairs.has(`${sourceKind}:${targetKind}`)
            ? null
            : 'edges must connect a Trigger to an Action or an Action to an Outcome',
        )
      }
    }
  })

  it('rejects an existing connection', () => {
    expect(
      connectError(node('trigger', 'source'), node('action', 'target'), [
        { source: 'source', target: 'target', sourceKind: 'trigger' },
      ]),
    ).toBe('these nodes are already connected')
  })

  it('rejects a second outgoing trigger edge', () => {
    expect(
      connectError(node('trigger', 'source'), node('action', 'target'), [
        { source: 'source', target: 'other', sourceKind: 'trigger' },
      ]),
    ).toBe('a Trigger can have only one outgoing edge')
  })

  it('rejects a second incoming trigger edge', () => {
    expect(
      connectError(node('trigger', 'source'), node('action', 'target'), [
        { source: 'other', target: 'target', sourceKind: 'trigger' },
      ]),
    ).toBe('an Action can have only one incoming Trigger edge')
  })

  it('allows independent action outcomes and trigger connections', () => {
    expect(
      connectError(node('action', 'action'), node('outcome', 'first'), [
        { source: 'action', target: 'other', sourceKind: 'action' },
      ]),
    ).toBeNull()
    expect(
      connectError(node('trigger', 'trigger'), node('action', 'action'), [
        { source: 'action', target: 'outcome', sourceKind: 'action' },
      ]),
    ).toBeNull()
  })

  it('reads a node kind from node data', () => {
    expect(kindOf({ data: { kind: 'outcome' } })).toBe('outcome')
    expect(kindOf({})).toBeUndefined()
  })
})
