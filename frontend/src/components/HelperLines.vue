<script setup lang="ts">
import { useVueFlow } from '@vue-flow/core'
import { computed, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  horizontal?: number
  vertical?: number
}>()

const { viewport, dimensions } = useVueFlow()
const canvasRef = ref<HTMLCanvasElement | null>(null)
const width = computed(() => dimensions.value.width)
const height = computed(() => dimensions.value.height)

function drawLines() {
  const canvas = canvasRef.value
  const context = canvas?.getContext('2d')
  if (!canvas || !context) return

  const dpi = window.devicePixelRatio
  canvas.width = width.value * dpi
  canvas.height = height.value * dpi
  context.scale(dpi, dpi)
  context.clearRect(0, 0, width.value, height.value)
  context.strokeStyle =
    getComputedStyle(canvas).getPropertyValue('--primary').trim() || '#00af79'

  if (typeof props.vertical === 'number') {
    context.beginPath()
    context.moveTo(props.vertical * viewport.value.zoom + viewport.value.x, 0)
    context.lineTo(
      props.vertical * viewport.value.zoom + viewport.value.x,
      height.value,
    )
    context.stroke()
  }
  if (typeof props.horizontal === 'number') {
    context.beginPath()
    context.moveTo(0, props.horizontal * viewport.value.zoom + viewport.value.y)
    context.lineTo(
      width.value,
      props.horizontal * viewport.value.zoom + viewport.value.y,
    )
    context.stroke()
  }
}

watch(
  [
    width,
    height,
    () => viewport.value.x,
    () => viewport.value.y,
    () => viewport.value.zoom,
    () => props.horizontal,
    () => props.vertical,
  ],
  drawLines,
  { immediate: true },
)

onMounted(drawLines)
</script>

<template>
  <canvas ref="canvasRef" class="vue-flow__helper-lines" />
</template>

<style scoped>
.vue-flow__helper-lines {
  position: absolute;
  inset: 0;
  z-index: 10;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
</style>
