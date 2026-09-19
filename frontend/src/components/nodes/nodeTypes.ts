import { markRaw } from 'vue'
import type { NodeTypesObject } from '@vue-flow/core'
import ActionNode from './ActionNode.vue'
import OutcomeNode from './OutcomeNode.vue'
import TriggerNode from './TriggerNode.vue'

export const nodeTypes: NodeTypesObject = {
  trigger: markRaw(TriggerNode),
  action: markRaw(ActionNode),
  outcome: markRaw(OutcomeNode),
}
