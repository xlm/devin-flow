<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import {
  VueFlow,
  useVueFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeDragEvent,
} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { ControlButton, Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { client } from '@/api/client'
import { useTheme } from '@/composables/useTheme'
import {
  connectError,
  kindOf,
  type CanvasEdge,
  type NodeKind,
} from '@/lib/connectRules'

const RESIZE_DEBOUNCE_MS = 100

const nodes = ref<Node[]>([])
const edges = ref<Edge[]>([])
const nodeSnapshots = new Map<string, Node>()
const edgeSnapshots = new Map<string, Edge>()
const dragPositions = new Map<string, { x: number; y: number }>()

const {
  fitView,
  findNode,
  addNodes,
  addEdges,
  getEdges,
  onNodeDragStart,
  onNodeDragStop,
  onNodesChange,
  onEdgesChange,
  onConnect,
} = useVueFlow()
const { mode, icon, cycleMode } = useTheme()

let resizeTimer: ReturnType<typeof setTimeout> | undefined

function nodeType(kind: NodeKind): string | undefined {
  if (kind === 'trigger') return 'input'
  if (kind === 'outcome') return 'output'
  return undefined
}

function nodeLabel(kind: NodeKind): string {
  return kind[0].toUpperCase() + kind.slice(1)
}

function mapNode(node: {
  id: string
  kind: NodeKind
  position: { x: number; y: number }
}): Node {
  return {
    id: node.id,
    type: nodeType(node.kind),
    position: { ...node.position },
    data: { kind: node.kind, label: nodeLabel(node.kind) },
  }
}

function mapEdge(edge: {
  id: string
  source: { id: string; kind: NodeKind }
  target: { id: string; kind: NodeKind }
}): Edge {
  return {
    id: edge.id,
    source: edge.source.id,
    target: edge.target.id,
    data: { sourceKind: edge.source.kind, targetKind: edge.target.kind },
  }
}

function copyNode(node: Node): Node {
  return { ...node, position: { ...node.position }, data: { ...node.data } }
}

function copyEdge(edge: Edge): Edge {
  return { ...edge, data: { ...edge.data } }
}

async function loadCanvas() {
  try {
    const { data } = await client.GET('/api/canvas')
    if (!data) return
    const loadedNodes = [
      ...data.trigger_nodes,
      ...data.action_nodes,
      ...data.outcome_nodes,
    ].map(mapNode)
    const loadedEdges = data.edges.map(mapEdge)
    nodes.value = loadedNodes
    edges.value = loadedEdges
    loadedNodes.forEach((node) => nodeSnapshots.set(node.id, copyNode(node)))
    loadedEdges.forEach((edge) => edgeSnapshots.set(edge.id, copyEdge(edge)))
  } catch {
    nodes.value = []
    edges.value = []
  }
}

async function saveNodePosition(event: NodeDragEvent) {
  const node = event.node
  const kind = kindOf(node)
  const before = dragPositions.get(node.id)
  if (!kind || !before) return
  try {
    const { error } = await client.PATCH('/api/canvas/nodes/{kind}/{node_id}', {
      params: { path: { kind, node_id: node.id } },
      body: { position: { x: node.position.x, y: node.position.y } },
    })
    if (error) {
      const current = findNode(node.id)
      if (current) current.position = { ...before }
    } else {
      nodeSnapshots.set(node.id, copyNode(node))
    }
  } catch {
    const current = findNode(node.id)
    if (current) current.position = { ...before }
  }
}

async function removeNode(change: Extract<NodeChange, { type: 'remove' }>) {
  const snapshot = nodeSnapshots.get(change.id) ?? findNode(change.id)
  if (!snapshot) return
  const kind = kindOf(snapshot)
  if (!kind) return
  try {
    const { error, response } = await client.DELETE(
      '/api/canvas/nodes/{kind}/{node_id}',
      { params: { path: { kind, node_id: snapshot.id } } },
    )
    if (error && response?.status !== 404) addNodes([copyNode(snapshot)])
  } catch {
    addNodes([copyNode(snapshot)])
  }
}

async function removeEdge(change: Extract<EdgeChange, { type: 'remove' }>) {
  const snapshot = edgeSnapshots.get(change.id)
  if (!snapshot) return
  try {
    const { error, response } = await client.DELETE(
      '/api/canvas/edges/{edge_id}',
      {
        params: { path: { edge_id: snapshot.id } },
      },
    )
    if (error && response?.status !== 404) addEdges([copyEdge(snapshot)])
  } catch {
    addEdges([copyEdge(snapshot)])
  }
}

function edgeCandidates(): Array<CanvasEdge & { sourceKind: NodeKind }> {
  const candidates: Array<CanvasEdge & { sourceKind: NodeKind }> = []
  getEdges.value.forEach((edge) => {
    const sourceKind = edge.data?.sourceKind as NodeKind | undefined
    if (sourceKind) {
      candidates.push({ source: edge.source, target: edge.target, sourceKind })
    }
  })
  return candidates
}

function connectionError(connection: Connection): string | null {
  const source = findNode(connection.source)
  const target = findNode(connection.target)
  const sourceKind = source && kindOf(source)
  const targetKind = target && kindOf(target)
  if (!sourceKind || !targetKind) return 'node not found'
  return connectError(
    { id: connection.source, kind: sourceKind },
    { id: connection.target, kind: targetKind },
    edgeCandidates(),
  )
}

function validConnection(connection: Connection): boolean {
  return connectionError(connection) === null
}

async function saveConnection(connection: Connection) {
  const error = connectionError(connection)
  if (error) return
  const source = findNode(connection.source)
  const target = findNode(connection.target)
  const sourceKind = kindOf(source!)!
  const targetKind = kindOf(target!)!
  try {
    const { data } = await client.POST('/api/canvas/edges', {
      body: {
        source: { id: connection.source, kind: sourceKind },
        target: { id: connection.target, kind: targetKind },
      },
    })
    if (data) {
      const edge = mapEdge(data)
      edgeSnapshots.set(edge.id, copyEdge(edge))
      addEdges([edge])
    }
  } catch {
    // The edge was never added locally, so there is nothing to revert.
  }
}

onNodeDragStart(({ node }) => {
  dragPositions.set(node.id, { ...node.position })
})
onNodeDragStop(saveNodePosition)
onNodesChange((changes) => {
  changes
    .filter((change): change is Extract<NodeChange, { type: 'remove' }> => {
      return change.type === 'remove'
    })
    .forEach((change) => void removeNode(change))
})
onEdgesChange((changes) => {
  changes
    .filter((change): change is Extract<EdgeChange, { type: 'remove' }> => {
      return change.type === 'remove'
    })
    .forEach((change) => void removeEdge(change))
})
onConnect(saveConnection)

// Vue Flow tracks pane dimensions itself; this only re-centers the graph
// once the user stops resizing the window.
function onWindowResize() {
  clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => fitView(), RESIZE_DEBOUNCE_MS)
}

onMounted(() => {
  void loadCanvas()
  window.addEventListener('resize', onWindowResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onWindowResize)
  clearTimeout(resizeTimer)
})
</script>

<template>
  <div class="h-screen w-screen">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      fit-view-on-init
      :is-valid-connection="validConnection"
    >
      <Background />
      <Controls position="top-left">
        <ControlButton
          :title="`Theme: ${mode}`"
          :aria-label="`Theme: ${mode}`"
          data-testid="theme-toggle"
          @click="cycleMode"
        >
          <component :is="icon" />
        </ControlButton>
      </Controls>
      <MiniMap
        position="bottom-right"
        pannable
        zoomable
        node-color="var(--muted-foreground)"
        node-stroke-color="var(--border)"
        mask-color="var(--vf-minimap-mask)"
        mask-stroke-color="var(--border)"
      />
    </VueFlow>
  </div>
</template>
