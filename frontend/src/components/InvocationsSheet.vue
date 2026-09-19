<script setup lang="ts">
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'

defineProps<{
  open: boolean
  title: string
  description: string
  testId: string
  loading: boolean
  loadError: boolean
  empty: boolean
}>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  retry: []
}>()
</script>

<template>
  <Sheet
    :open="open"
    :data-testid="`${testId}-sheet`"
    @update:open="emit('update:open', $event)"
  >
    <SheetContent side="right">
      <SheetHeader>
        <SheetTitle>{{ title }}</SheetTitle>
        <SheetDescription>{{ description }}</SheetDescription>
      </SheetHeader>
      <div class="flex-1 overflow-y-auto px-4">
        <p v-if="loading" class="text-sm text-muted-foreground">Loading...</p>
        <div
          v-else-if="loadError"
          role="alert"
          :data-testid="`${testId}-error`"
          class="flex items-center gap-3 text-sm text-destructive"
        >
          <span>Could not load invocations</span>
          <button
            type="button"
            :data-testid="`${testId}-retry`"
            class="rounded-md border px-2 py-1 text-xs"
            @click="emit('retry')"
          >
            Retry
          </button>
        </div>
        <p
          v-else-if="empty"
          :data-testid="`${testId}-empty`"
          class="text-sm text-muted-foreground"
        >
          No invocations yet
        </p>
        <template v-else>
          <slot />
        </template>
      </div>
    </SheetContent>
  </Sheet>
</template>
