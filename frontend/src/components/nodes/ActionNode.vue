<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import type { NodeProps } from '@vue-flow/core'
import { useVueFlow } from '@vue-flow/core'
import { actionFieldsFromData, actionInvalidReason } from '@/lib/actionValidity'
import { SAVE_NODE_FIELDS } from '@/lib/canvasInjection'
import { usePlaybooks } from '@/composables/usePlaybooks'
import CanvasNodeShell from './CanvasNodeShell.vue'

const props = defineProps<NodeProps>()
const saveNodeFields = inject(SAVE_NODE_FIELDS, async () => false)
const { edges } = useVueFlow()
const { playbooks, loading, error, reload } = usePlaybooks()
const saveError = ref(false)

const fields = computed(() => actionFieldsFromData(props.data))
const reason = computed(() =>
  actionInvalidReason(props.id, fields.value, edges.value),
)
const unknownPlaybook = computed(() => {
  if (
    !fields.value.playbookId ||
    playbooks.value.some((playbook) => playbook.id === fields.value.playbookId)
  ) {
    return null
  }
  return fields.value.playbookId
})

async function saveName(event: Event) {
  saveError.value = !(await saveNodeFields(props.id, {
    name: (event.target as HTMLInputElement).value,
  }))
}

async function savePlaybook(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  saveError.value = !(await saveNodeFields(props.id, {
    playbookId: value || null,
  }))
}

async function saveInstructions(event: Event) {
  saveError.value = !(await saveNodeFields(props.id, {
    extraInstructions: (event.target as HTMLTextAreaElement).value,
  }))
}
</script>

<template>
  <CanvasNodeShell
    :id="id"
    kind="action"
    :complete="reason === null"
    :status="reason === 'no-trigger' ? 'No Trigger' : undefined"
    :hint="
      reason === 'no-trigger' ? 'Connect a Trigger to this Action' : undefined
    "
  >
    <template #toolbar>
      <button
        type="button"
        role="switch"
        aria-checked="false"
        disabled
        data-testid="enable-switch"
        title="Enabling the Automation activates in a later ticket"
        aria-label="Enable Automation"
        class="rounded-full border px-2 py-0.5 text-xs"
      >
        Enable
      </button>
    </template>
    <p
      v-if="saveError"
      role="alert"
      data-testid="save-error"
      class="text-xs text-destructive"
    >
      Could not save
    </p>
    <div class="space-y-2 text-xs">
      <label class="block">
        <span class="sr-only">Action name</span>
        <input
          data-testid="action-name"
          class="nodrag w-full rounded-md border bg-background px-2 py-1"
          maxlength="200"
          :value="fields.name"
          @change="saveName"
        />
      </label>
      <label class="block">
        <span class="sr-only">Playbook</span>
        <select
          data-testid="action-playbook"
          class="nodrag w-full rounded-md border bg-background px-2 py-1"
          :value="fields.playbookId ?? ''"
          @change="savePlaybook"
        >
          <option value="">Choose a Playbook</option>
          <option v-if="unknownPlaybook" :value="unknownPlaybook">
            Unknown Playbook ({{ unknownPlaybook }})
          </option>
          <option
            v-for="playbook in playbooks"
            :key="playbook.id"
            :value="playbook.id"
          >
            {{ playbook.title }}
          </option>
        </select>
      </label>
      <div v-if="loading" class="text-muted-foreground">
        Loading Playbooks...
      </div>
      <div v-if="error" class="flex items-center gap-2 text-destructive">
        <span>Could not load playbooks.</span>
        <button
          type="button"
          data-testid="playbooks-retry"
          class="underline"
          @click="reload"
        >
          Retry
        </button>
      </div>
      <label class="block">
        <span class="sr-only">Extra instructions</span>
        <textarea
          data-testid="action-instructions"
          class="nodrag nowheel w-full rounded-md border bg-background px-2 py-1"
          rows="3"
          maxlength="20000"
          :value="fields.extraInstructions"
          @change="saveInstructions"
        />
      </label>
    </div>
  </CanvasNodeShell>
</template>
