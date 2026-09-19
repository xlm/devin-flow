<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { NodeProps } from '@vue-flow/core'
import { useVueFlow } from '@vue-flow/core'
import { client } from '@/api/client'
import {
  type EventAction,
  type TriggerRead,
  type TriggerUpdate,
} from '@/lib/connectRules'
import { isRepositoryFullName } from '@/lib/repository'
import CanvasNodeShell from './CanvasNodeShell.vue'

type TriggerData = {
  kind: 'trigger'
  label: string
  trigger?: TriggerRead
}

const props = defineProps<NodeProps<TriggerData>>()
const { updateNodeData } = useVueFlow()

const eventAction = ref<EventAction | ''>('')
const repository = ref('')
const repositories = ref<string[] | null>(null)
const repositoriesError = ref(false)
const loadingRepositories = ref(true)
const saveError = ref(false)
const repositoryInvalid = ref(false)
let saveChain = Promise.resolve()

const complete = computed(() => Boolean(eventAction.value && repository.value))
const repositoryOptions = computed(() => {
  const values = repositories.value ? [...repositories.value] : []
  if (repository.value && !values.includes(repository.value)) {
    values.push(repository.value)
  }
  return values
})

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
  const snapshot: TriggerRead = {
    event_action: props.data.trigger?.event_action ?? null,
    repository_full_name: props.data.trigger?.repository_full_name ?? null,
  }
  const next = saveChain.then(async () => {
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
    } catch {
      revert(snapshot)
    }
  })
  saveChain = next
  return next
}

function saveRepositoryInput() {
  repositoryInvalid.value = false
  if (repository.value === '') {
    void save({ repository_full_name: null })
    return
  }
  if (!isRepositoryFullName(repository.value)) {
    repositoryInvalid.value = true
    return
  }
  void save({ repository_full_name: repository.value })
}

watch(
  () => props.data?.trigger,
  (trigger) => syncFromData(trigger),
  { deep: true, immediate: true },
)
onMounted(() => void loadRepositories())
</script>

<template>
  <CanvasNodeShell :id="id" kind="trigger" :complete="complete">
    <div class="mt-2 flex flex-col gap-1">
      <select
        v-model="eventAction"
        data-testid="trigger-event"
        class="nodrag rounded-md border bg-background px-2 py-1 text-xs"
        @change="save({ event_action: eventAction || null })"
      >
        <option value="" disabled>Select event</option>
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
      <template v-else-if="!repositoriesError">
        <select
          v-model="repository"
          data-testid="trigger-repository"
          class="nodrag rounded-md border bg-background px-2 py-1 text-xs"
          @change="save({ repository_full_name: repository || null })"
        >
          <option value="" disabled>Select repository</option>
          <option v-for="repo in repositoryOptions" :key="repo" :value="repo">
            {{ repo }}
          </option>
        </select>
      </template>
      <template v-else>
        <input
          v-model="repository"
          data-testid="trigger-repository-input"
          placeholder="owner/repo"
          class="nodrag rounded-md border bg-background px-2 py-1 text-xs"
          @change="saveRepositoryInput"
          @blur="saveRepositoryInput"
        />
        <span
          v-if="repositoryInvalid"
          data-testid="trigger-repository-invalid"
          class="text-xs text-destructive"
        >
          Use owner/repo
        </span>
        <button
          type="button"
          data-testid="trigger-repositories-retry"
          class="rounded-md border bg-background px-2 py-1 text-xs"
          @click="loadRepositories"
        >
          Retry
        </button>
      </template>
      <span v-if="saveError" role="alert" class="text-xs text-destructive">
        Could not save
      </span>
    </div>
  </CanvasNodeShell>
</template>
