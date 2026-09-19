<script setup lang="ts">
import type { NodeProps } from '@vue-flow/core'
import CanvasNodeShell from './CanvasNodeShell.vue'

defineProps<NodeProps>()
</script>

<template>
  <CanvasNodeShell :id="id" kind="trigger" />
</template>
