<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import type { NodeProps } from '@vue-flow/core'
import { useVueFlow } from '@vue-flow/core'
import { client } from '@/api/client'
import type { OutcomeKind, OutcomeRead } from '@/lib/connectRules'
import { REFRESH_SYNC_STATE } from '@/lib/canvasInjection'
import { OUTCOME_KINDS, outcomeKindLabel } from '@/lib/outcomeKinds'
import CanvasNodeShell from './CanvasNodeShell.vue'

type OutcomeData = {
  kind: 'outcome'
  label: string
  outcome?: OutcomeRead
}

const props = defineProps<NodeProps<OutcomeData>>()
const { updateNodeData } = useVueFlow()
const refreshSyncState = inject(REFRESH_SYNC_STATE, async () => {})

const kind = ref<OutcomeKind | ''>('')
const saveError = ref(false)
let saveChain = Promise.resolve()

const complete = computed(() => Boolean(props.data.outcome?.kind))

function revert(previous: OutcomeKind | null) {
  kind.value = previous ?? ''
  saveError.value = true
}

function save(value: OutcomeKind | null) {
  const next = saveChain.then(async () => {
    const previous = props.data.outcome?.kind ?? null
    try {
      const { data, error } = await client.PATCH(
        '/api/canvas/nodes/{kind}/{node_id}',
        {
          params: { path: { kind: 'outcome', node_id: props.id } },
          body: { outcome: { kind: value } },
        },
      )
      if (error || !data) {
        revert(previous)
        return
      }
      saveError.value = false
      updateNodeData(props.id, { outcome: data.outcome })
      await refreshSyncState()
    } catch {
      revert(previous)
    }
  })
  saveChain = next
  return next
}

watch(
  () => props.data?.outcome,
  (outcome) => {
    kind.value = outcome?.kind ?? ''
  },
  { immediate: true },
)
</script>

<template>
  <CanvasNodeShell :id="id" kind="outcome" :complete="complete">
    <div class="mt-2 flex flex-col gap-1">
      <select
        v-model="kind"
        data-testid="outcome-kind"
        class="nodrag rounded-md border bg-background px-2 py-1 text-xs"
        @change="save(kind || null)"
      >
        <option value="">Select kind</option>
        <option v-for="option in OUTCOME_KINDS" :key="option" :value="option">
          {{ outcomeKindLabel(option) }}
        </option>
      </select>
      <span v-if="saveError" role="alert" class="text-xs text-destructive">
        Could not save
      </span>
    </div>
  </CanvasNodeShell>
</template>
