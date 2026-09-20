import type { GraphNode, NodePositionChange, XYPosition } from '@vue-flow/core'

export interface HelperLines {
  horizontal?: number
  vertical?: number
  snapPosition: Partial<XYPosition>
}

export function getHelperLines(
  change: NodePositionChange,
  nodes: GraphNode[],
  distance = 5,
): HelperLines {
  const result: HelperLines = {
    snapPosition: {},
  }
  const nodeA = nodes.find((node) => node.id === change.id)
  if (!nodeA || !change.position) return result

  const widthA = Number(nodeA.dimensions.width ?? nodeA.width ?? 0)
  const heightA = Number(nodeA.dimensions.height ?? nodeA.height ?? 0)
  const boundsA = {
    left: change.position.x,
    right: change.position.x + widthA,
    top: change.position.y,
    bottom: change.position.y + heightA,
  }
  let horizontalDistance = distance
  let verticalDistance = distance

  for (const nodeB of nodes) {
    if (nodeB.id === nodeA.id) continue
    const widthB = Number(nodeB.dimensions.width ?? nodeB.width ?? 0)
    const heightB = Number(nodeB.dimensions.height ?? nodeB.height ?? 0)
    const boundsB = {
      left: nodeB.position.x,
      right: nodeB.position.x + widthB,
      top: nodeB.position.y,
      bottom: nodeB.position.y + heightB,
    }
    const verticalAlignments = [
      [boundsA.left, boundsB.left, boundsB.left],
      [boundsA.right, boundsB.right, boundsB.right - widthA],
      [boundsA.left, boundsB.right, boundsB.right],
      [boundsA.right, boundsB.left, boundsB.left - widthA],
    ]
    for (const [current, target, snap] of verticalAlignments) {
      const candidateDistance = Math.abs(current - target)
      if (candidateDistance < verticalDistance) {
        verticalDistance = candidateDistance
        result.vertical = target
        result.snapPosition.x = snap
      }
    }

    const horizontalAlignments = [
      [boundsA.top, boundsB.top, boundsB.top],
      [boundsA.bottom, boundsB.top, boundsB.top - heightA],
      [boundsA.bottom, boundsB.bottom, boundsB.bottom - heightA],
      [boundsA.top, boundsB.bottom, boundsB.bottom],
    ]
    for (const [current, target, snap] of horizontalAlignments) {
      const candidateDistance = Math.abs(current - target)
      if (candidateDistance < horizontalDistance) {
        horizontalDistance = candidateDistance
        result.horizontal = target
        result.snapPosition.y = snap
      }
    }
  }

  return result
}
