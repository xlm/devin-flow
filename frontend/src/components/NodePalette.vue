<script setup lang="ts">
import {
  NODE_KIND_MIME,
  NODE_KINDS,
  nodeAccentClass,
  nodeHint,
  nodeLabel,
} from '@/lib/nodeKinds'
import type { NodeKind } from '@/lib/connectRules'

const props = withDefaults(
  defineProps<{
    disabled?: boolean
  }>(),
  { disabled: false },
)

function onDragStart(event: DragEvent, kind: NodeKind) {
  event.dataTransfer?.setData(NODE_KIND_MIME, kind)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}
</script>

<template>
  <aside
    data-testid="node-palette"
    class="bg-sidebar text-sidebar-foreground border-sidebar-border flex w-48 shrink-0 flex-col gap-2 border-r p-3"
  >
    <h2 class="text-sm font-medium">Devin Flow</h2>
    <div
      v-for="kind in NODE_KINDS"
      :key="kind"
      :data-testid="`palette-${kind}`"
      role="listitem"
      :draggable="!props.disabled"
      :aria-disabled="props.disabled"
      class="rounded-md border border-border border-l-4 bg-card p-2 shadow-sm"
      :class="[
        nodeAccentClass(kind),
        props.disabled ? 'cursor-not-allowed opacity-50' : 'cursor-grab',
      ]"
      @dragstart="onDragStart($event, kind)"
    >
      <div class="text-sm font-medium">{{ nodeLabel(kind) }}</div>
      <div class="text-xs text-muted-foreground">{{ nodeHint(kind) }}</div>
    </div>
  </aside>
</template>
