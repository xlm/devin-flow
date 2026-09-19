import { ref, type Ref } from 'vue'
import { client } from '@/api/client'
import type { components } from '@/api/schema'

export type PlaybookOption = components['schemas']['PlaybookOption']

const playbooks = ref<PlaybookOption[]>([])
const loading = ref(false)
const error = ref(false)
let loaded = false
let request: Promise<void> | undefined

function fetchPlaybooks(): Promise<void> {
  loading.value = true
  error.value = false
  request = client
    .GET('/api/devin/playbooks')
    .then(({ data, error: apiError }) => {
      if (apiError || !data) {
        error.value = true
        return
      }
      playbooks.value = data
    })
    .catch(() => {
      error.value = true
    })
    .finally(() => {
      loading.value = false
      loaded = true
      request = undefined
    })
  return request
}

function ensurePlaybooks(): Promise<void> {
  if (request) return request
  if (loaded) return Promise.resolve()
  return fetchPlaybooks()
}

export function usePlaybooks(): {
  playbooks: Readonly<Ref<PlaybookOption[]>>
  loading: Ref<boolean>
  error: Ref<boolean>
  reload: () => Promise<void>
} {
  void ensurePlaybooks()
  return {
    playbooks,
    loading,
    error,
    reload: async () => {
      loaded = false
      await fetchPlaybooks()
    },
  }
}

export function resetPlaybooksCache(): void {
  playbooks.value = []
  loading.value = false
  error.value = false
  loaded = false
  request = undefined
}
