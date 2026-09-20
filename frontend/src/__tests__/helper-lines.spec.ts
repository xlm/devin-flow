import type { GraphNode, NodePositionChange } from '@vue-flow/core'
import { describe, expect, it } from 'vitest'
import { getHelperLines } from '@/lib/helperLines'

function node(
  id: string,
  x: number,
  y: number,
  width = 20,
  height = 10,
): GraphNode {
  return {
    id,
    position: { x, y },
    dimensions: { width, height },
  } as GraphNode
}

function change(id: string, x: number, y: number): NodePositionChange {
  return {
    id,
    type: 'position',
    position: { x, y },
    from: { x, y },
  }
}

describe('getHelperLines', () => {
  it('returns no lines without candidates', () => {
    expect(getHelperLines(change('a', 0, 0), [node('a', 0, 0)])).toEqual({
      snapPosition: {},
    })
  })

  it('returns no lines when the dragged node is missing', () => {
    expect(getHelperLines(change('missing', 0, 0), [node('a', 0, 0)])).toEqual({
      snapPosition: {},
    })
  })

  it('uses fallback node dimensions', () => {
    const dragged = {
      ...node('a', 101, 0),
      dimensions: { width: undefined, height: undefined },
      width: 20,
      height: 10,
    } as unknown as GraphNode
    const candidate = {
      ...node('b', 100, 0),
      dimensions: { width: undefined, height: undefined },
      width: 20,
      height: 10,
    } as unknown as GraphNode
    const result = getHelperLines(change('a', 101, 0), [
      dragged,
      candidate,
      {
        ...candidate,
        id: 'empty',
        width: undefined,
        height: undefined,
      } as unknown as GraphNode,
    ])
    expect(result.vertical).toBe(100)
  })

  it('uses fallback dimensions for the dragged node', () => {
    const dragged = {
      ...node('a', 81, 0),
      dimensions: { width: undefined, height: undefined },
      width: 20,
      height: 10,
    } as unknown as GraphNode
    const result = getHelperLines(change('a', 81, 0), [
      dragged,
      node('b', 100, 0),
    ])
    expect(result.vertical).toBe(100)
    expect(result.snapPosition.x).toBe(80)

    const emptyDragged = {
      ...node('empty', 0, 100),
      dimensions: { width: undefined, height: undefined },
      width: undefined,
      height: undefined,
    } as unknown as GraphNode
    expect(
      getHelperLines(change('empty', 0, 100), [
        emptyDragged,
        node('b', 100, 0),
      ]),
    ).toEqual({ snapPosition: {} })
  })

  it.each([
    ['left edge', 101, 0, 100, 100],
    ['right edge', 99, 0, 100, 100],
    ['left to right', 121, 0, 120, 120],
    ['right to left', 81, 0, 100, 80],
  ])('snaps %s vertically', (_label, x, y, line, snap) => {
    const result = getHelperLines(change('a', x, y), [
      node('a', x, y),
      node('b', 100, 0),
    ])
    expect(result.vertical).toBe(line)
    expect(result.snapPosition.x).toBe(snap)
  })

  it.each([
    ['top edge', 0, 51, 50, 50],
    ['bottom to top', 0, 44, 50, 40],
    ['bottom edge', 0, 49, 59, 49],
    ['top to bottom', 0, 61, 60, 60],
  ])('snaps %s horizontally', (_label, x, y, line, snap) => {
    const candidate =
      _label === 'bottom edge' ? node('b', 0, 40, 20, 19) : node('b', 0, 50)
    const result = getHelperLines(change('a', x, y), [
      node('a', x, y),
      candidate,
    ])
    expect(result.horizontal).toBe(line)
    expect(result.snapPosition.y).toBe(snap)
  })

  it('does not snap outside the distance threshold', () => {
    const result = getHelperLines(
      change('a', 106, 0),
      [node('a', 106, 0), node('b', 100, 0)],
      5,
    )
    expect(result.vertical).toBeUndefined()
    expect(result.snapPosition.x).toBeUndefined()
  })

  it('ignores the dragged node itself', () => {
    const result = getHelperLines(change('a', 0, 0), [
      node('a', 0, 0),
      node('b', 200, 200),
    ])
    expect(result).toEqual({ snapPosition: {} })
  })
})
