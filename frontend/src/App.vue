<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Button } from '@/components/ui/button'

const status = ref<'loading' | 'ok' | 'error'>('loading')

onMounted(async () => {
  try {
    const response = await fetch('/api/health')
    status.value = response.ok ? 'ok' : 'error'
  } catch {
    status.value = 'error'
  }
})
</script>

<template>
  <main class="flex min-h-screen flex-col items-center justify-center gap-4">
    <h1 class="text-2xl font-semibold">devin-flow</h1>
    <Button>Get started</Button>
    <p>API: {{ status }}</p>
  </main>
</template>
