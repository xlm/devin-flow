<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { client } from '@/api/client'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import type { OutcomeInvocationRead, OutcomeKind } from '@/lib/connectRules'
import { outcomeKindLabel } from '@/lib/outcomeKinds'

const props = defineProps<{
  open: boolean
  nodeId: string | null
  kind: OutcomeKind | null
}>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const invocations = ref<OutcomeInvocationRead[]>([])
const loading = ref(false)
const loadError = ref(false)

const title = computed(() =>
  props.kind ? `${outcomeKindLabel(props.kind)} outcomes` : 'Outcome',
)

async function load() {
  if (!props.nodeId) return
  loading.value = true
  loadError.value = false
  try {
    const { data, error } = await client.GET(
      '/api/outcome-nodes/{node_id}/invocations',
      { params: { path: { node_id: props.nodeId } } },
    )
    if (error || !data) {
      loadError.value = true
    } else {
      invocations.value = data
    }
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.open, props.nodeId] as const,
  ([open]) => {
    if (open) void load()
  },
  { immediate: true },
)

function formatDate(value: string): string {
  return new Date(value).toLocaleString()
}
</script>

<template>
  <Sheet
    :open="open"
    data-testid="outcome-sheet"
    @update:open="emit('update:open', $event)"
  >
    <SheetContent side="right">
      <SheetHeader>
        <SheetTitle>{{ title }}</SheetTitle>
        <SheetDescription>
          Invocations that produced this outcome
        </SheetDescription>
      </SheetHeader>
      <div class="flex-1 overflow-y-auto px-4">
        <p v-if="loading" class="text-sm text-muted-foreground">Loading...</p>
        <div
          v-else-if="loadError"
          role="alert"
          data-testid="outcome-error"
          class="flex items-center gap-3 text-sm text-destructive"
        >
          <span>Could not load invocations</span>
          <button
            type="button"
            data-testid="outcome-retry"
            class="rounded-md border px-2 py-1 text-xs"
            @click="load"
          >
            Retry
          </button>
        </div>
        <p
          v-else-if="invocations.length === 0"
          data-testid="outcome-empty"
          class="text-sm text-muted-foreground"
        >
          No invocations yet
        </p>
        <ul v-else class="flex flex-col gap-3">
          <li
            v-for="invocation in invocations"
            :key="invocation.id"
            data-testid="outcome-invocation"
            class="rounded-md border p-2 text-sm"
          >
            <div class="font-medium">
              {{ invocation.title ?? invocation.session_id }}
            </div>
            <a
              v-if="invocation.url"
              :href="invocation.url"
              target="_blank"
              rel="noopener"
              class="text-xs text-primary underline"
              >Session</a
            >
            <div class="text-xs text-muted-foreground">
              {{ invocation.status }} -
              {{ formatDate(invocation.session_created_at) }}
            </div>
            <ul v-if="invocation.pull_requests.length" class="mt-1">
              <li
                v-for="pr in invocation.pull_requests"
                :key="pr.url"
                class="flex items-center gap-2 text-xs"
              >
                <a
                  :href="pr.url"
                  target="_blank"
                  rel="noopener"
                  class="text-primary underline"
                  >{{ pr.url }}</a
                >
                <span
                  class="rounded-full border px-1.5 py-0.5 text-[0.65rem] uppercase"
                  >{{ pr.state }}</span
                >
              </li>
            </ul>
            <a
              v-if="invocation.duplicate_of"
              :href="invocation.duplicate_of"
              target="_blank"
              rel="noopener"
              class="mt-1 inline-block text-xs text-primary underline"
              >Duplicate of</a
            >
          </li>
        </ul>
      </div>
    </SheetContent>
  </Sheet>
</template>
