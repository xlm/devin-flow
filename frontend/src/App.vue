<script setup lang="ts">
import { ref } from 'vue'
import FlowCanvas from '@/components/FlowCanvas.vue'
import { Button } from '@/components/ui/button'
import { useApiHealth, type IndicatorTone } from '@/composables/useApiHealth'

const { indicator } = useApiHealth()
const archivedOpen = ref(false)

const DOT_CLASS: Record<IndicatorTone, string> = {
  loading: 'bg-muted-foreground/50',
  green: 'bg-emerald-500',
  amber: 'bg-amber-500',
  red: 'bg-red-500',
}
</script>

<template>
  <main class="relative">
    <FlowCanvas v-model:archived-open="archivedOpen" />
    <div class="absolute top-4 right-4 z-10 flex items-center gap-2">
      <p
        role="status"
        data-testid="api-status"
        :data-tone="indicator.tone"
        :title="indicator.title"
        class="bg-card text-muted-foreground pointer-events-none flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs"
      >
        <span
          aria-hidden="true"
          class="size-2 rounded-full"
          :class="DOT_CLASS[indicator.tone]"
        />
        {{ indicator.label }}
      </p>
      <Button
        size="sm"
        variant="outline"
        data-testid="archived-actions-button"
        @click="archivedOpen = true"
      >
        Archived
      </Button>
    </div>
  </main>
</template>
