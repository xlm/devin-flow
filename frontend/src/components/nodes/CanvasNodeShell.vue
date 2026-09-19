<script setup lang="ts">
import { Trash2 } from '@lucide/vue'
import { Handle, Position, useVueFlow } from '@vue-flow/core'
import { NodeToolbar } from '@vue-flow/node-toolbar'
import { Button } from '@/components/ui/button'
import {
  NODE_HANDLES,
  nodeAccentClass,
  nodeHint,
  nodeLabel,
} from '@/lib/nodeKinds'
import type { NodeKind } from '@/lib/connectRules'

const props = withDefaults(
  defineProps<{
    id: string
    kind: NodeKind
    complete?: boolean
  }>(),
  { complete: false },
)

const { removeNodes } = useVueFlow()
</script>

<template>
  <NodeToolbar :node-id="props.id" :position="Position.Top">
    <Button
      variant="destructive"
      size="icon-xs"
      aria-label="Delete node"
      data-testid="delete-node"
      @click="removeNodes([props.id])"
    >
      <Trash2 />
    </Button>
  </NodeToolbar>
  <div
    data-testid="canvas-node"
    :data-kind="props.kind"
    :data-incomplete="String(!props.complete)"
    class="min-w-40 rounded-md border-2 border-l-4 bg-card px-3 py-2 text-card-foreground"
    :class="[nodeAccentClass(props.kind), !props.complete && 'border-dashed']"
  >
    <div class="text-sm font-medium">{{ nodeLabel(props.kind) }}</div>
    <slot />
    <span class="text-xs uppercase text-muted-foreground">{{
      props.complete ? 'Ready' : 'Incomplete'
    }}</span>
    <div v-if="!props.complete" class="text-xs text-muted-foreground">
      {{ nodeHint(props.kind) }}
    </div>
  </div>
  <Handle
    v-if="NODE_HANDLES[props.kind].target"
    type="target"
    :position="Position.Left"
  />
  <Handle
    v-if="NODE_HANDLES[props.kind].source"
    type="source"
    :position="Position.Right"
  />
</template>
