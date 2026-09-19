<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
import type { NodeProps } from '@vue-flow/core'
import { useVueFlow } from '@vue-flow/core'
import { client } from '@/api/client'
import {
  type EventAction,
  type TriggerRead,
  type TriggerUpdate,
} from '@/lib/connectRules'
import { REFRESH_SYNC_STATE } from '@/lib/canvasInjection'
import CanvasNodeShell from './CanvasNodeShell.vue'

type TriggerData = {
  kind: 'trigger'
  label: string
  trigger?: TriggerRead
}

const props = defineProps<NodeProps<TriggerData>>()
const { updateNodeData } = useVueFlow()
const refreshSyncState = inject(REFRESH_SYNC_STATE, async () => {})

const eventAction = ref<EventAction | ''>('')
const repository = ref('')
const repositories = ref<string[] | null>(null)
const repositoriesError = ref(false)
const loadingRepositories = ref(true)
const saveError = ref(false)
let saveChain = Promise.resolve()

const complete = computed(() =>
  Boolean(
    props.data.trigger?.event_action &&
    props.data.trigger?.repository_full_name,
  ),
)
const repositoryOptions = computed(() => {
  const values = repositories.value ? [...repositories.value] : []
  if (repository.value && !values.includes(repository.value)) {
    values.push(repository.value)
  }
  return values
})
const repositoryHint = computed(() =>
  loadingRepositories.value
    ? undefined
    : repositoriesError.value
      ? 'Could not load repositories'
      : repositoryOptions.value.length === 0
        ? 'No eligible repositories'
        : undefined,
)

function syncFromData(trigger: TriggerRead | undefined) {
  eventAction.value = trigger?.event_action ?? ''
  repository.value = trigger?.repository_full_name ?? ''
}

async function loadRepositories() {
  loadingRepositories.value = true
  repositoriesError.value = false
  try {
    const { data, error } = await client.GET('/api/devin/repositories')
    if (error || !data) {
      repositoriesError.value = true
      repositories.value = null
    } else {
      repositories.value = data.map((repo) => repo.repo_path)
    }
  } catch {
    repositoriesError.value = true
    repositories.value = null
  } finally {
    loadingRepositories.value = false
  }
}

function revert(snapshot: TriggerRead) {
  syncFromData(snapshot)
  saveError.value = true
}

function save(patch: TriggerUpdate) {
  const next = saveChain.then(async () => {
    const snapshot: TriggerRead = {
      event_action: props.data.trigger?.event_action ?? null,
      repository_full_name: props.data.trigger?.repository_full_name ?? null,
    }
    try {
      const { data, error } = await client.PATCH(
        '/api/canvas/nodes/{kind}/{node_id}',
        {
          params: { path: { kind: 'trigger', node_id: props.id } },
          body: { trigger: patch },
        },
      )
      if (error || !data) {
        revert(snapshot)
        return
      }
      saveError.value = false
      updateNodeData(props.id, { trigger: data.trigger })
      await refreshSyncState()
    } catch {
      revert(snapshot)
    }
  })
  saveChain = next
  return next
}

watch(
  () => props.data?.trigger,
  (trigger) => syncFromData(trigger),
  { deep: true, immediate: true },
)
onMounted(() => void loadRepositories())
</script>

<template>
  <CanvasNodeShell
    :id="id"
    kind="trigger"
    :complete="complete"
    :hint="repositoryHint"
  >
    <div class="mt-2 flex flex-col gap-1">
      <select
        v-model="eventAction"
        data-testid="trigger-event"
        class="nodrag rounded-md border bg-background px-2 py-1 text-xs"
        @change="save({ event_action: eventAction || null })"
      >
        <option value="">Select event</option>
        <option value="opened">opened</option>
        <option value="closed">closed</option>
      </select>
      <select
        v-if="loadingRepositories"
        disabled
        class="rounded-md border bg-background px-2 py-1 text-xs"
      >
        <option>Loading repositories...</option>
      </select>
      <select
        v-else
        v-model="repository"
        data-testid="trigger-repository"
        class="nodrag rounded-md border bg-background px-2 py-1 text-xs"
        @change="save({ repository_full_name: repository || null })"
      >
        <option value="">Select repository</option>
        <option v-for="repo in repositoryOptions" :key="repo" :value="repo">
          {{ repo }}
        </option>
      </select>
      <button
        v-if="repositoriesError"
        type="button"
        data-testid="trigger-repositories-retry"
        class="rounded-md border bg-background px-2 py-1 text-xs"
        @click="loadRepositories"
      >
        Retry
      </button>
      <span v-if="saveError" role="alert" class="text-xs text-destructive">
        Could not save
      </span>
    </div>
  </CanvasNodeShell>
</template>
