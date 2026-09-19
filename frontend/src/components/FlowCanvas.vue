<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { VueFlow, useVueFlow, type Edge, type Node } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { ControlButton, Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { useTheme } from '@/composables/useTheme'

const RESIZE_DEBOUNCE_MS = 100

const nodes = ref<Node[]>([
  {
    id: '1',
    type: 'input',
    position: { x: 0, y: 0 },
    data: { label: 'Start' },
  },
  { id: '2', position: { x: 250, y: 100 }, data: { label: 'Process' } },
  {
    id: '3',
    type: 'output',
    position: { x: 500, y: 0 },
    data: { label: 'End' },
  },
])

const edges = ref<Edge[]>([
  { id: 'e1-2', source: '1', target: '2', animated: true },
  { id: 'e2-3', source: '2', target: '3', animated: true },
])

const { fitView } = useVueFlow()
const { mode, icon, cycleMode } = useTheme()

let resizeTimer: ReturnType<typeof setTimeout> | undefined

// Vue Flow tracks pane dimensions itself; this only re-centers the graph
// once the user stops resizing the window.
function onWindowResize() {
  clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => fitView(), RESIZE_DEBOUNCE_MS)
}

onMounted(() => {
  window.addEventListener('resize', onWindowResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onWindowResize)
  clearTimeout(resizeTimer)
})
</script>

<template>
  <div class="h-screen w-screen">
    <VueFlow :nodes="nodes" :edges="edges" fit-view-on-init>
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
