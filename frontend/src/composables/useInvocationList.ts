import { ref, type Ref } from 'vue'

type FetchResult<T> = { data?: T[]; error?: unknown }

export function useInvocationList<T>(fetcher: () => Promise<FetchResult<T>>): {
  items: Ref<T[]>
  loading: Ref<boolean>
  loadError: Ref<boolean>
  load: () => Promise<void>
} {
  const items = ref<T[]>([]) as Ref<T[]>
  const loading = ref(false)
  const loadError = ref(false)
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

  return { items, loading, loadError, load }
}
