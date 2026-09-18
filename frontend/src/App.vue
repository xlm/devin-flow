<script setup lang="ts">
import { onMounted, ref } from 'vue'
import FlowCanvas from '@/components/FlowCanvas.vue'
import { client } from '@/api/client'

const status = ref<'loading' | 'ok' | 'error'>('loading')

onMounted(async () => {
  try {
    const { data } = await client.GET('/api/health')
    status.value = data?.status === 'ok' ? 'ok' : 'error'
  } catch {
    status.value = 'error'
  }
})
</script>

<template>
  <main class="relative">
    <FlowCanvas />
    <p
      class="bg-card text-muted-foreground pointer-events-none absolute top-4 right-4 z-10 rounded-md border px-2 py-1 text-xs"
    >
      API: {{ status }}
    </p>
  </main>
</template>
