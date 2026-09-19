import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'
import { client } from '@/api/client'
import type { components } from '@/api/schema'

export type PollingStatus = components['schemas']['PollingStatus']
export type ApiHealthState = 'loading' | 'error' | 'ok'
export type IndicatorTone = 'loading' | 'green' | 'amber' | 'red'

export const HEALTH_POLL_INTERVAL_MS = 15_000

const state = ref<ApiHealthState>('loading')
const polling = ref<PollingStatus | undefined>()
let request: Promise<void> | undefined
let timer: ReturnType<typeof setInterval> | undefined
let subscribers = 0

export function refreshApiHealth(): Promise<void> {
  if (request) return request
  request = client
    .GET('/api/health')
    .then(({ data, error }) => {
      if (error || data?.status !== 'ok') {
        state.value = 'error'
        return
      }
      state.value = 'ok'
      polling.value = data.polling
    })
    .catch(() => {
      state.value = 'error'
    })
    .finally(() => {
      request = undefined
    })
  return request
}

export interface Indicator {
  tone: IndicatorTone
  label: string
  title: string
}

function formatTime(value: string | null): string {
  return value === null ? 'never' : new Date(value).toLocaleTimeString()
}

function describe(): Indicator {
  if (state.value === 'loading') {
    return { tone: 'loading', label: 'Connecting', title: 'Checking the API' }
  }
  if (state.value === 'error') {
    return { tone: 'red', label: 'API error', title: 'Health request failed' }
  }
  const status = polling.value
  if (!status || !status.enabled) {
    return {
      tone: 'amber',
      label: 'Polling off',
      title: 'Invocation polling is disabled, use Refresh to sync',
    }
  }
  const title = `Last poll ${formatTime(status.last_success_at)}, every ${status.interval_seconds}s`
  return status.stale
    ? { tone: 'amber', label: 'Polling stale', title }
    : { tone: 'green', label: 'Live', title }
}

export function useApiHealth(intervalMs = HEALTH_POLL_INTERVAL_MS): {
  state: Readonly<Ref<ApiHealthState>>
  polling: Readonly<Ref<PollingStatus | undefined>>
  indicator: ComputedRef<Indicator>
  refresh: () => Promise<void>
} {
  subscribers += 1
  if (timer === undefined) {
    void refreshApiHealth()
    timer = setInterval(() => void refreshApiHealth(), intervalMs)
  }
  onScopeDispose(() => {
    subscribers -= 1
    if (subscribers === 0 && timer !== undefined) {
      clearInterval(timer)
      timer = undefined
    }
  })
  return {
    state,
    polling,
    indicator: computed(describe),
    refresh: refreshApiHealth,
  }
}

export function resetApiHealth(): void {
  if (timer !== undefined) clearInterval(timer)
  timer = undefined
  subscribers = 0
  request = undefined
  state.value = 'loading'
  polling.value = undefined
}
