<script setup lang="ts">
import {
  BaseEdge,
  Position,
  getSmoothStepPath,
  type EdgeProps,
} from '@vue-flow/core'
import { computed } from 'vue'

const props = defineProps<EdgeProps>()

const geometry = computed(() => {
  const [path, centerX, centerY] = getSmoothStepPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
  })
  const horizontal =
    props.targetPosition === Position.Left ||
    props.targetPosition === Position.Right
  return {
    path,
    labelX: horizontal ? (centerX + props.targetX) / 2 : props.targetX,
    labelY: horizontal ? props.targetY : (centerY + props.targetY) / 2,
  }
})
</script>

<template>
  <BaseEdge
    :id="id"
    :path="geometry.path"
    :label="label"
    :label-x="geometry.labelX"
    :label-y="geometry.labelY"
    :marker-end="markerEnd"
    :marker-start="markerStart"
    :style="style"
    :label-style="labelStyle"
    :label-show-bg="labelShowBg"
    :label-bg-style="labelBgStyle"
    :label-bg-padding="labelBgPadding"
    :label-bg-border-radius="labelBgBorderRadius"
    :interaction-width="interactionWidth"
  />
</template>
