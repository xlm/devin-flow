<script setup lang="ts">
import { computed, onMounted, onUnmounted, provide, ref } from 'vue'
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
import { RefreshCw } from '@lucide/vue'
import { client } from '@/api/client'
import { Button } from '@/components/ui/button'
import NodePalette from '@/components/NodePalette.vue'
import ActionInvocationsSheet from '@/components/ActionInvocationsSheet.vue'
import OutcomeInvocationsSheet from '@/components/OutcomeInvocationsSheet.vue'
import { nodeTypes } from '@/components/nodes/nodeTypes'
import { refreshApiHealth } from '@/composables/useApiHealth'
import { useTheme } from '@/composables/useTheme'
import {
  actionFieldsOf,
  syncStateFromData,
  type ActionFields,
  type ActionNodeRead,
} from '@/lib/actionValidity'
import {
  REFRESH_SYNC_STATE,
  SAVE_NODE_FIELDS,
  type RefreshSyncState,
  type SaveNodeFields,
} from '@/lib/canvasInjection'
import {
  connectError,
  kindOf,
  type CanvasEdge,
  type EdgeCreate,
  type EdgeRead,
  type NodeKind,
  type NodeRead,
  type NodeRef,
  type OutcomeKind,
  type OutcomeRead,
  type Position,
} from '@/lib/connectRules'
import { isNodeKind, NODE_KIND_MIME, nodeLabel } from '@/lib/nodeKinds'
import { outcomeCountLabel } from '@/lib/outcomeKinds'

const RESIZE_DEBOUNCE_MS = 100

const nodes = ref<Node[]>([])
const edges = ref<Edge[]>([])
const loadError = ref(false)
const loading = ref(false)
const refreshing = ref(false)
const creationBlocked = computed(() => loading.value || loadError.value)
const nodeSnapshots = new Map<string, Node>()
const edgeSnapshots = new Map<string, Edge>()
const saveGenerations = new Map<string, number>()
const saveChains = new Map<string, Promise<void | boolean>>()
const pendingFields = new Map<string, Map<string, number>>()
const cascadedNodeIds = new Set<string>()
let loadPromise: Promise<void> | undefined

const {
  fitView,
  findNode,
  addEdges,
  addNodes,
  getEdges,
  onNodeDragStop,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onEdgeClick,
  screenToFlowCoordinate,
} = useVueFlow()
const { mode, icon, cycleMode } = useTheme()

let resizeTimer: ReturnType<typeof setTimeout> | undefined

function mapNode(node: NodeRead | ActionNodeRead): Node {
  let data: Record<string, unknown> = {
    kind: node.kind,
    label: nodeLabel(node.kind),
  }
  if (node.kind === 'trigger') data.trigger = node.trigger
  if (node.kind === 'outcome') data.outcome = node.outcome
  if ('name' in node) {
    data = {
      ...data,
      ...actionFieldsOf(node),
      syncStatus: node.sync_status,
      syncError: node.sync_error,
      invocationCount: node.invocation_count,
    }
  }
  return {
    id: node.id,
    type: node.kind,
    position: { ...node.position },
    data,
  }
}

function invocationLabel(count: number): string {
  return `${count} ${count === 1 ? 'invocation' : 'invocations'}`
}

function mapEdge(edge: EdgeRead, counts: Map<string, number>): Edge {
  const mapped: Edge = {
    id: edge.id,
    source: edge.source.id,
    target: edge.target.id,
    data: { sourceKind: edge.source.kind, targetKind: edge.target.kind },
  }
  if (edge.target.kind === 'action') {
    mapped.label = invocationLabel(counts.get(edge.target.id) ?? 0)
    mapped.class = 'cursor-pointer'
  }
  if (edge.target.kind === 'outcome') {
    mapped.label = outcomeCountLabel(edge.outcome_count ?? 0)
    mapped.class = 'cursor-pointer'
  }
  return mapped
}

function invocationCounts(actions: ActionNodeRead[]): Map<string, number> {
  return new Map(actions.map((action) => [action.id, action.invocation_count]))
}

function copyNode(node: Node): Node {
  return { ...node, position: { ...node.position }, data: { ...node.data } }
}

function copyEdge(edge: Edge): Edge {
  return { ...edge, data: { ...edge.data } }
}

async function fetchCanvas() {
  loadError.value = false
  loading.value = true
  nodeSnapshots.clear()
  edgeSnapshots.clear()
  saveGenerations.clear()
  saveChains.clear()
  pendingFields.clear()
  cascadedNodeIds.clear()
  try {
    const { data, error } = await client.GET('/api/canvas')
    if (error || !data) {
      loadError.value = true
      nodes.value = []
      edges.value = []
      return
    }
    const loadedNodes = [
      ...data.trigger_nodes,
      ...data.action_nodes,
      ...data.outcome_nodes,
    ].map(mapNode)
    const counts = invocationCounts(data.action_nodes)
    const loadedEdges = data.edges.map((edge) => mapEdge(edge, counts))
    nodes.value = loadedNodes
    edges.value = loadedEdges
    loadedNodes.forEach((node) => nodeSnapshots.set(node.id, copyNode(node)))
    loadedEdges.forEach((edge) => edgeSnapshots.set(edge.id, copyEdge(edge)))
  } catch {
    loadError.value = true
    nodes.value = []
    edges.value = []
  } finally {
    loading.value = false
  }
}

function loadCanvas(): Promise<void> {
  if (!loadPromise) {
    loadPromise = fetchCanvas().finally(() => {
      loadPromise = undefined
    })
  }
  return loadPromise
}

async function doSaveNodePosition(
  node: Node,
  kind: NodeKind,
  position: Position,
  generation: number,
) {
  try {
    const { error } = await client.PATCH('/api/canvas/nodes/{kind}/{node_id}', {
      params: { path: { kind, node_id: node.id } },
      body: { position },
    })
    if (!error) {
      const savedNode = copyNode(nodeSnapshots.get(node.id) ?? node)
      savedNode.position = { ...position }
      nodeSnapshots.set(node.id, savedNode)
      return
    }
    if (generation !== saveGenerations.get(node.id)) return
    const savedPosition = nodeSnapshots.get(node.id)?.position
    if (!savedPosition) return
    const current = findNode(node.id)
    if (current) current.position = { ...savedPosition }
  } catch {
    if (generation !== saveGenerations.get(node.id)) return
    const savedPosition = nodeSnapshots.get(node.id)?.position
    if (!savedPosition) return
    const current = findNode(node.id)
    if (current) current.position = { ...savedPosition }
  }
}

function saveNodePosition(event: NodeDragEvent): Promise<void> | undefined {
  const node = event.node
  const kind = kindOf(node)
  if (!kind) return
  const position = { ...node.position }
  const generation = (saveGenerations.get(node.id) ?? 0) + 1
  saveGenerations.set(node.id, generation)
  const savedNode = copyNode(node)
  savedNode.position = { ...position }
  const previous = saveChains.get(node.id) ?? Promise.resolve()
  const next = previous.then(() =>
    doSaveNodePosition(savedNode, kind, position, generation),
  )
  saveChains.set(
    node.id,
    next.catch(() => {}),
  )
  return next
}

async function doSaveNodeFields(
  node: Node,
  kind: NodeKind,
  fields: Partial<ActionFields>,
): Promise<boolean> {
  const body: {
    name?: string
    playbook_id?: string | null
    prompt?: string
    enabled?: boolean
  } = {}
  if (fields.name !== undefined) body.name = fields.name
  if (fields.playbookId !== undefined) body.playbook_id = fields.playbookId
  if (fields.prompt !== undefined) {
    body.prompt = fields.prompt
  }
  if (fields.enabled !== undefined) body.enabled = fields.enabled
  let failed = false
  try {
    const { data, error } = await client.PATCH(
      '/api/canvas/nodes/{kind}/{node_id}',
      {
        params: { path: { kind, node_id: node.id } },
        body,
      },
    )
    if (!error) {
      const base = nodeSnapshots.get(node.id) ?? copyNode(node)
      base.data = { ...base.data, ...fields }
      if (data && 'sync_status' in data) {
        const sync = syncStateFromData({
          syncStatus: data.sync_status,
          syncError: data.sync_error,
        })
        base.data = {
          ...base.data,
          enabled: data.enabled,
          syncStatus: sync.status,
          syncError: sync.error,
        }
        const current = findNode(node.id)
        if (current) current.data = { ...current.data, ...base.data }
      }
      nodeSnapshots.set(node.id, base)
    } else {
      failed = true
    }
  } catch {
    failed = true
  } finally {
    const pending = pendingFields.get(node.id)
    for (const field of Object.keys(fields)) {
      const count = pending?.get(field) ?? 0
      if (count > 1) {
        pending?.set(field, count - 1)
      } else {
        pending?.delete(field)
      }
    }
    if (pending && pending.size === 0) pendingFields.delete(node.id)
  }
  if (failed) {
    const snapshot = nodeSnapshots.get(node.id)
    const current = findNode(node.id)
    const pending = pendingFields.get(node.id)
    if (snapshot && current) {
      const data = { ...current.data }
      for (const field of Object.keys(fields)) {
        if ((pending?.get(field) ?? 0) === 0) {
          data[field] = snapshot.data[field]
        }
      }
      current.data = data
    }
  }
  return !failed
}

const saveNodeFields: SaveNodeFields = async (
  nodeId: string,
  fields: Partial<ActionFields>,
) => {
  const node = findNode(nodeId)
  if (!node) return false
  const kind = kindOf(node)
  if (!kind) return false
  const pending = pendingFields.get(nodeId) ?? new Map<string, number>()
  for (const field of Object.keys(fields)) {
    pending.set(field, (pending.get(field) ?? 0) + 1)
  }
  pendingFields.set(nodeId, pending)
  node.data = { ...node.data, ...fields }
  const optimistic = copyNode(node)
  const previous = saveChains.get(nodeId) ?? Promise.resolve()
  const next = previous.then(() => doSaveNodeFields(optimistic, kind, fields))
  saveChains.set(
    nodeId,
    next.catch(() => {}),
  )
  return next
}

provide(SAVE_NODE_FIELDS, saveNodeFields)

async function refreshSyncState() {
  try {
    const { data, error } = await client.GET('/api/canvas')
    if (error || !data) return
    data.action_nodes.forEach((action) => {
      const sync = syncStateFromData({
        syncStatus: action.sync_status,
        syncError: action.sync_error,
      })
      const count = action.invocation_count
      const current = findNode(action.id)
      if (current) {
        current.data = {
          ...current.data,
          enabled: action.enabled,
          syncStatus: sync.status,
          syncError: sync.error,
          invocationCount: count,
        }
      }
      const snapshot = nodeSnapshots.get(action.id)
      if (snapshot) {
        snapshot.data = {
          ...snapshot.data,
          enabled: action.enabled,
          syncStatus: sync.status,
          syncError: sync.error,
          invocationCount: count,
        }
      }
      getEdges.value
        .filter((edge) => edge.target === action.id)
        .forEach((edge) => {
          edge.label = invocationLabel(count)
        })
    })
    data.edges
      .filter((edge) => edge.target.kind === 'outcome')
      .forEach((edge) => {
        const current = getEdges.value.find((item) => item.id === edge.id)
        if (current) {
          current.label = outcomeCountLabel(edge.outcome_count ?? 0)
        }
      })
  } catch {
    return
  }
}

provide<RefreshSyncState>(REFRESH_SYNC_STATE, refreshSyncState)

async function removeNode(change: Extract<NodeChange, { type: 'remove' }>) {
  const snapshot = nodeSnapshots.get(change.id) ?? findNode(change.id)
  if (!snapshot) {
    cascadedNodeIds.delete(change.id)
    return
  }
  const kind = kindOf(snapshot)
  if (!kind) {
    cascadedNodeIds.delete(change.id)
    return
  }
  try {
    const { error, response } = await client.DELETE(
      '/api/canvas/nodes/{kind}/{node_id}',
      { params: { path: { kind, node_id: snapshot.id } } },
    )
    if (error && response?.status !== 404) {
      await loadCanvas()
    } else {
      edgeSnapshots.forEach((edge) => {
        if (edge.source === snapshot.id || edge.target === snapshot.id) {
          edgeSnapshots.delete(edge.id)
        }
      })
      if (!error && kind === 'trigger') await refreshSyncState()
    }
  } catch {
    await loadCanvas()
  } finally {
    cascadedNodeIds.delete(snapshot.id)
  }
}

async function removeEdge(change: Extract<EdgeChange, { type: 'remove' }>) {
  await Promise.resolve()
  const snapshot = edgeSnapshots.get(change.id)
  if (!snapshot) return
  if (
    cascadedNodeIds.has(snapshot.source) ||
    cascadedNodeIds.has(snapshot.target)
  ) {
    return
  }
  try {
    const { error, response } = await client.DELETE(
      '/api/canvas/edges/{edge_id}',
      {
        params: { path: { edge_id: snapshot.id } },
      },
    )
    if (!error || response?.status === 404) {
      edgeSnapshots.delete(snapshot.id)
      await refreshSyncState()
    } else {
      addEdges([copyEdge(snapshot)])
    }
  } catch {
    addEdges([copyEdge(snapshot)])
  }
}

function edgeCandidates(
  excludeId?: string,
): Array<CanvasEdge & { sourceKind: NodeKind }> {
  const candidates: Array<CanvasEdge & { sourceKind: NodeKind }> = []
  getEdges.value.forEach((edge) => {
    const sourceKind = edge.data?.sourceKind as NodeKind | undefined
    if (sourceKind && edge.id !== excludeId) {
      candidates.push({ source: edge.source, target: edge.target, sourceKind })
    }
  })
  return candidates
}

function resolveConnection(connection: Connection): EdgeCreate | null {
  const source = findNode(connection.source)
  const target = findNode(connection.target)
  const sourceKind = source && kindOf(source)
  const targetKind = target && kindOf(target)
  if (!sourceKind || !targetKind) return null
  const sourceRef: NodeRef = {
    id: connection.source,
    kind: sourceKind,
  }
  const targetRef: NodeRef = {
    id: connection.target,
    kind: targetKind,
  }
  return {
    source: sourceRef,
    target: targetRef,
  }
}

function connectionError(connection: Connection | Edge): string | null {
  const resolved = resolveConnection(connection)
  if (!resolved) return 'node not found'
  // Vue Flow also validates existing edges when the edge list is replaced,
  // so an edge must not count as a duplicate of itself
  const ownId = 'id' in connection ? connection.id : undefined
  return connectError(resolved.source, resolved.target, edgeCandidates(ownId))
}

function validConnection(connection: Connection | Edge): boolean {
  return connectionError(connection) === null
}

async function saveConnection(connection: Connection) {
  const refs = resolveConnection(connection)
  if (!refs || connectError(refs.source, refs.target, edgeCandidates())) return
  try {
    const { data } = await client.POST('/api/canvas/edges', {
      body: refs,
    })
    if (data) {
      // refreshSyncState below fills in the real invocation count
      const edge = mapEdge(data, new Map())
      edgeSnapshots.set(edge.id, copyEdge(edge))
      addEdges([edge])
      await refreshSyncState()
    }
  } catch {
    // The edge was never added locally, so there is nothing to revert.
  }
}

async function retryLoad() {
  await loadCanvas()
  await refreshApiHealth()
}

async function refreshInvocations() {
  refreshing.value = true
  try {
    await client.POST('/api/invocations/refresh')
  } catch {
    // A failed refresh still reloads so the canvas shows what is stored.
  } finally {
    refreshing.value = false
  }
  await Promise.all([loadCanvas(), refreshApiHealth()])
}

async function createNode(kind: NodeKind, position: Position) {
  try {
    const { data } = await client.POST('/api/canvas/nodes/{kind}', {
      params: { path: { kind } },
      body: { position },
    })
    if (data) {
      if (loadPromise) await loadPromise
      if (loadError.value || findNode(data.id)) return
      const node = mapNode(data)
      nodeSnapshots.set(node.id, copyNode(node))
      addNodes([node])
    }
  } catch {
    // The node was never added locally, so there is nothing to revert.
  }
}

function onDragOver(event: DragEvent) {
  if (creationBlocked.value) return
  if (!event.dataTransfer?.types.includes(NODE_KIND_MIME)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
}

function onDrop(event: DragEvent) {
  if (creationBlocked.value) return
  if (!event.dataTransfer?.types.includes(NODE_KIND_MIME)) return
  const kind = event.dataTransfer.getData(NODE_KIND_MIME)
  if (!isNodeKind(kind)) return
  event.preventDefault()
  const position = screenToFlowCoordinate({
    x: event.clientX,
    y: event.clientY,
  })
  void createNode(kind, position)
}

onNodeDragStop(saveNodePosition)
onNodesChange((changes) => {
  changes
    .filter((change): change is Extract<NodeChange, { type: 'remove' }> => {
      return change.type === 'remove'
    })
    .forEach((change) => {
      cascadedNodeIds.add(change.id)
      void removeNode(change)
    })
})
onEdgesChange((changes) => {
  changes
    .filter((change): change is Extract<EdgeChange, { type: 'remove' }> => {
      return change.type === 'remove'
    })
    .forEach((change) => void removeEdge(change))
})
onConnect(saveConnection)

const outcomeSheetOpen = ref(false)
const selectedOutcomeId = ref<string | null>(null)
const selectedActionId = ref<string | null>(null)
const selectedOutcomeKind = ref<OutcomeKind | null>(null)
const actionSheetOpen = ref(false)
const selectedActionSheetId = ref<string | null>(null)
const selectedActionName = ref<string | null>(null)

onEdgeClick((event) => {
  if (event.edge.data?.targetKind === 'action') {
    selectedActionSheetId.value = event.edge.target
    const actionData = findNode(event.edge.target)?.data
    selectedActionName.value =
      typeof actionData?.name === 'string' ? actionData.name : null
    actionSheetOpen.value = true
    return
  }
  if (event.edge.data?.targetKind !== 'outcome') return
  selectedOutcomeId.value = event.edge.target
  selectedActionId.value = event.edge.source
  selectedOutcomeKind.value =
    (findNode(event.edge.target)?.data?.outcome as OutcomeRead | undefined)
      ?.kind ?? null
  outcomeSheetOpen.value = true
})

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
  <div class="flex h-screen w-screen">
    <NodePalette :disabled="creationBlocked" />
    <div
      class="relative min-w-0 flex-1"
      data-testid="canvas-drop-zone"
      @dragover="onDragOver"
      @drop="onDrop"
    >
      <div
        v-if="loadError"
        role="alert"
        data-testid="load-error"
        class="absolute top-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-3 rounded-md border border-destructive bg-background px-4 py-2 text-sm text-destructive shadow"
      >
        <span>Could not load the Canvas.</span>
        <Button
          size="sm"
          variant="outline"
          data-testid="load-retry"
          @click="retryLoad"
        >
          Retry
        </Button>
      </div>
      <VueFlow
        class="h-full"
        :nodes="nodes"
        :edges="edges"
        :node-types="nodeTypes"
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
          <ControlButton
            title="Refresh invocations"
            aria-label="Refresh invocations"
            data-testid="refresh-invocations"
            :disabled="refreshing"
            @click="refreshInvocations"
          >
            <RefreshCw />
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
      <OutcomeInvocationsSheet
        v-model:open="outcomeSheetOpen"
        :node-id="selectedOutcomeId"
        :action-node-id="selectedActionId"
        :kind="selectedOutcomeKind"
      />
      <ActionInvocationsSheet
        v-model:open="actionSheetOpen"
        :node-id="selectedActionSheetId"
        :action-name="selectedActionName"
      />
    </div>
  </div>
</template>
