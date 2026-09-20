<script setup lang="ts">
import { watch } from 'vue'
import { client } from '@/api/client'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { useInvocationList } from '@/composables/useInvocationList'
import type { ArchivedActionRead, Position } from '@/lib/connectRules'
import { formatDate } from '@/lib/formatDate'
import { ARCHIVED_ACTION_MIME } from '@/lib/nodeKinds'

const props = defineProps<{
  open: boolean
}>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  restore: [id: string, position?: Position]
}>()

const {
  items: actions,
  loading,
  loadError,
  load,
} = useInvocationList<ArchivedActionRead>(() =>
  client.GET('/api/canvas/archived-actions'),
)

function onDragStart(event: DragEvent, id: string) {
  event.dataTransfer?.setData(ARCHIVED_ACTION_MIME, id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function remove(id: string) {
  actions.value = actions.value.filter((action) => action.id !== id)
}

defineExpose({ remove })

watch(
  () => props.open,
  (open) => {
    if (open) void load()
  },
  { immediate: true },
)
</script>

<template>
  <!-- Non-modal so rows can be dragged onto the canvas behind the sheet. -->
  <Sheet
    :open="open"
    :modal="false"
    data-testid="archived-sheet"
    @update:open="emit('update:open', $event)"
  >
    <SheetContent side="right">
      <SheetHeader>
        <SheetTitle>Archived actions</SheetTitle>
        <SheetDescription>
          Drag an action onto the Canvas or restore it in place
        </SheetDescription>
      </SheetHeader>
      <div class="flex-1 overflow-y-auto px-4">
        <p v-if="loading" class="text-sm text-muted-foreground">Loading...</p>
        <div
          v-else-if="loadError"
          role="alert"
          data-testid="archived-error"
          class="flex items-center gap-3 text-sm text-destructive"
        >
          <span>Could not load archived actions</span>
          <button
            type="button"
            data-testid="archived-retry"
            class="rounded-md border px-2 py-1 text-xs"
            @click="load"
          >
            Retry
          </button>
        </div>
        <p
          v-else-if="actions.length === 0"
          data-testid="archived-empty"
          class="text-sm text-muted-foreground"
        >
          No archived actions
        </p>
        <ul v-else class="flex flex-col gap-3">
          <li
            v-for="action in actions"
            :key="action.id"
            data-testid="archived-action"
            :data-id="action.id"
            draggable="true"
            class="cursor-grab rounded-md border p-2 text-sm"
            @dragstart="onDragStart($event, action.id)"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="font-medium">{{
                action.name.trim() || 'Untitled action'
              }}</span>
              <Button
                size="sm"
                variant="outline"
                data-testid="archived-restore"
                @click="emit('restore', action.id)"
              >
                Restore
              </Button>
            </div>
            <div class="text-xs text-muted-foreground">
              {{ action.playbook_id ?? 'No playbook' }}
            </div>
            <div class="text-xs text-muted-foreground">
              {{ action.invocation_count }} invocations - archived
              {{ formatDate(action.archived_at) }}
            </div>
          </li>
        </ul>
      </div>
    </SheetContent>
  </Sheet>
</template>
