import { ref, type Ref } from 'vue'
import { client } from '@/api/client'

type FetchResult<T> = { data?: T[]; error?: unknown }

export function useInvocationList<T>(fetcher: () => Promise<FetchResult<T>>): {
  items: Ref<T[]>
  loading: Ref<boolean>
  loadError: Ref<boolean>
  load: () => Promise<void>
  archivingIds: Ref<Set<string>>
  archiveErrors: Ref<Set<string>>
  archive: (id: string) => Promise<boolean>
} {
  const items = ref<T[]>([]) as Ref<T[]>
  const loading = ref(false)
  const loadError = ref(false)
  const archivingIds = ref(new Set<string>())
  const archiveErrors = ref(new Set<string>())
  // Out-of-order responses must not overwrite a newer node's data.
  let generation = 0

  async function load() {
    const current = ++generation
    loading.value = true
    loadError.value = false
    try {
      const { data, error } = await fetcher()
      if (current !== generation) return
      if (error || !data) {
        loadError.value = true
      } else {
        items.value = data
      }
    } catch {
      if (current !== generation) return
      loadError.value = true
    } finally {
      if (current === generation) loading.value = false
    }
  }

  async function archive(id: string): Promise<boolean> {
    archivingIds.value.add(id)
    archiveErrors.value.delete(id)
    try {
      const { error } = await client.POST(
        '/api/invocations/{invocation_id}/archive',
        {
          params: { path: { invocation_id: id } },
        },
      )
      if (error) {
        archiveErrors.value.add(id)
        return false
      }
      await load()
      return true
    } catch {
      archiveErrors.value.add(id)
      return false
    } finally {
      archivingIds.value.delete(id)
    }
  }

  return {
    items,
    loading,
    loadError,
    load,
    archivingIds,
    archiveErrors,
    archive,
  }
}
