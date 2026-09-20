<script setup lang="ts">
import { computed, watch } from 'vue'
import { client } from '@/api/client'
import InvocationsSheet from '@/components/InvocationsSheet.vue'
import { Button } from '@/components/ui/button'
import { useInvocationList } from '@/composables/useInvocationList'
import type { ActionInvocationRead, IssueRef } from '@/lib/connectRules'
import { formatDate } from '@/lib/formatDate'
import { sessionStatusBadgeClass } from '@/lib/sessionStatus'

const props = defineProps<{
  open: boolean
  nodeId: string | null
  actionName: string | null
}>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  archived: []
}>()

const {
  items: invocations,
  loading,
  loadError,
  load,
  archivingIds,
  archiveErrors,
  archive,
} = useInvocationList<ActionInvocationRead>(() =>
  client.GET('/api/action-nodes/{node_id}/invocations', {
    // `load` only runs while nodeId is set; the watch below guards it.
    params: { path: { node_id: props.nodeId as string } },
  }),
)

async function archiveInvocation(id: string) {
  if (await archive(id)) emit('archived')
}

const title = computed(
  () => `${props.actionName?.trim() || 'Action'} invocations`,
)

function issueLabel(issue: IssueRef): string {
  const parts = [
    issue.number === null ? null : `#${issue.number}`,
    issue.title,
  ].filter((part): part is string => part !== null && part !== '')
  return parts.length ? parts.join(' ') : issue.url
}

watch(
  () => [props.open, props.nodeId] as const,
  ([open, nodeId]) => {
    if (open && nodeId) void load()
  },
  { immediate: true },
)
</script>

<template>
  <InvocationsSheet
    :open="open"
    :title="title"
    description="Sessions started by this Action, newest first"
    test-id="action"
    :loading="loading"
    :load-error="loadError"
    :empty="invocations.length === 0"
    @update:open="emit('update:open', $event)"
    @retry="load"
  >
    <ul class="flex flex-col gap-3">
      <li
        v-for="invocation in invocations"
        :key="invocation.id"
        data-testid="action-invocation"
        class="rounded-md border p-2 text-sm"
      >
        <a
          v-if="invocation.issue"
          :href="invocation.issue.url"
          target="_blank"
          rel="noopener"
          class="text-xs text-primary underline"
          >{{ issueLabel(invocation.issue) }}</a
        >
        <div v-else class="text-xs text-muted-foreground">Issue unknown</div>
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
        <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            data-testid="session-status-dot"
            aria-hidden="true"
            class="inline-block size-2 shrink-0 rounded-full"
            :class="sessionStatusBadgeClass(invocation.status)"
          />
          <span
            >{{ invocation.status }} -
            {{ formatDate(invocation.session_created_at) }}</span
          >
        </div>
        <div class="mt-2 flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            data-testid="archive-invocation"
            aria-label="Archive session"
            :disabled="
              archivingIds.has(invocation.id) || invocation.archived_at !== null
            "
            @click="archiveInvocation(invocation.id)"
          >
            {{ invocation.archived_at ? 'Archived' : 'Archive' }}
          </Button>
          <span
            v-if="archiveErrors.has(invocation.id)"
            data-testid="archive-error"
            class="text-xs text-destructive"
            >Could not archive session</span
          >
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
      </li>
    </ul>
  </InvocationsSheet>
</template>
