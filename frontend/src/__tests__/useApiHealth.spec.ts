import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { effectScope } from 'vue'

const GET = vi.hoisted(() => vi.fn())

vi.mock('@/api/client', () => ({
  client: { GET },
}))

import {
  HEALTH_POLL_INTERVAL_MS,
  refreshApiHealth,
  resetApiHealth,
  useApiHealth,
  type PollingStatus,
} from '@/composables/useApiHealth'

function health(polling: Partial<PollingStatus> = {}) {
  return {
    data: {
      status: 'ok',
      polling: {
        enabled: true,
        interval_seconds: 60,
        last_success_at: '2026-01-01T12:00:00Z',
        stale: false,
        ...polling,
      },
    },
    error: undefined,
  }
}

function mountHealth() {
  const scope = effectScope()
  const state = scope.run(() => useApiHealth())
  if (!state) throw new Error('scope did not run')
  return { scope, ...state }
}

describe('useApiHealth', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    resetApiHealth()
    GET.mockReset()
    vi.useRealTimers()
  })

  it('starts as loading and turns green when the poller is live', async () => {
    GET.mockResolvedValue(health())
    const { checkedAt, indicator, state } = mountHealth()
    expect(state.value).toBe('loading')
    expect(indicator.value.tone).toBe('loading')
    await flushPromises()
    expect(state.value).toBe('ok')
    expect(checkedAt.value).not.toBe(0)
    expect(indicator.value).toMatchObject({ tone: 'green', label: 'Live' })
    expect(indicator.value.title).toContain('every 60s')
    expect(indicator.value.title).not.toContain('never')
  })

  it('shows amber Polling stale when the poller has not succeeded recently', async () => {
    GET.mockResolvedValue(health({ stale: true, last_success_at: null }))
    const { indicator } = mountHealth()
    await flushPromises()
    expect(indicator.value).toMatchObject({
      tone: 'amber',
      label: 'Polling stale',
    })
    expect(indicator.value.title).toContain('never')
  })

  it('shows amber Polling off when polling is disabled', async () => {
    GET.mockResolvedValue(
      health({ enabled: false, interval_seconds: 0, stale: false }),
    )
    const { indicator } = mountHealth()
    await flushPromises()
    expect(indicator.value).toMatchObject({
      tone: 'amber',
      label: 'Polling off',
    })
  })

  it('shows red API error on a rejected request, an error response and a bad status', async () => {
    GET.mockRejectedValue(new Error('down'))
    const { checkedAt, indicator, state } = mountHealth()
    await flushPromises()
    expect(state.value).toBe('error')
    expect(checkedAt.value).toBe(0)
    expect(indicator.value).toMatchObject({ tone: 'red', label: 'API error' })

    GET.mockResolvedValue({ data: undefined, error: { detail: 'nope' } })
    await refreshApiHealth()
    expect(state.value).toBe('error')

    GET.mockResolvedValue({ data: { status: 'down' }, error: undefined })
    await refreshApiHealth()
    expect(state.value).toBe('error')
  })

  it('does not update checkedAt for unhealthy responses', async () => {
    GET.mockResolvedValue(health())
    const { checkedAt } = mountHealth()
    await flushPromises()
    const firstCheckedAt = checkedAt.value
    expect(firstCheckedAt).not.toBe(0)

    GET.mockResolvedValue({ data: undefined, error: { detail: 'nope' } })
    await refreshApiHealth()
    expect(checkedAt.value).toBe(firstCheckedAt)

    GET.mockResolvedValue({ data: { status: 'down' }, error: undefined })
    await refreshApiHealth()
    expect(checkedAt.value).toBe(firstCheckedAt)

    GET.mockRejectedValue(new Error('down'))
    await refreshApiHealth()
    expect(checkedAt.value).toBe(firstCheckedAt)
  })

  it('recovers from error to green on the next poll without a reload', async () => {
    GET.mockRejectedValueOnce(new Error('down'))
    GET.mockResolvedValue(health())
    const { indicator } = mountHealth()
    await flushPromises()
    expect(indicator.value.tone).toBe('red')
    await vi.advanceTimersByTimeAsync(HEALTH_POLL_INTERVAL_MS)
    expect(indicator.value.tone).toBe('green')
    expect(GET).toHaveBeenCalledTimes(2)
  })

  it('shares one request and one timer across subscribers', async () => {
    GET.mockResolvedValue(health())
    const first = mountHealth()
    const second = mountHealth()
    await Promise.all([first.refresh(), second.refresh()])
    await flushPromises()
    expect(GET).toHaveBeenCalledTimes(1)
    first.scope.stop()
    await vi.advanceTimersByTimeAsync(HEALTH_POLL_INTERVAL_MS)
    expect(GET).toHaveBeenCalledTimes(2)
    second.scope.stop()
    await vi.advanceTimersByTimeAsync(HEALTH_POLL_INTERVAL_MS)
    expect(GET).toHaveBeenCalledTimes(2)
  })

  it('treats a missing polling payload as Polling off', async () => {
    GET.mockResolvedValue({ data: { status: 'ok' }, error: undefined })
    const { indicator } = mountHealth()
    await flushPromises()
    expect(indicator.value.label).toBe('Polling off')
  })
})
