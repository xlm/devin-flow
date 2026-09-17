<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Button } from '@/components/ui/button'
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
  <main class="flex min-h-screen flex-col items-center justify-center gap-4">
    <h1 class="text-2xl font-semibold">devin-flow</h1>
    <Button>Get started</Button>
    <p>API: {{ status }}</p>
  </main>
</template>
