import type { InjectionKey } from 'vue'
import type { ActionFields } from '@/lib/actionValidity'

export type SaveNodeFields = (
  nodeId: string,
  fields: Partial<ActionFields>,
) => Promise<void>

export const SAVE_NODE_FIELDS: InjectionKey<SaveNodeFields> =
  Symbol('saveNodeFields')
