import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

const GET = vi.hoisted(() => vi.fn())

vi.mock('@/api/client', () => ({
  client: { GET },
}))

import { resetPlaybooksCache, usePlaybooks } from '@/composables/usePlaybooks'

describe('usePlaybooks', () => {
  afterEach(() => {
    resetPlaybooksCache()
    GET.mockReset()
  })

  it('loads playbooks successfully', async () => {
    GET.mockResolvedValue({
      data: [{ id: 'pb-1', title: 'Triage' }],
      error: undefined,
    })
    const state = usePlaybooks()
    await flushPromises()
    expect(state.playbooks.value).toEqual([{ id: 'pb-1', title: 'Triage' }])
    expect(state.error.value).toBe(false)
    expect(state.loading.value).toBe(false)
    usePlaybooks()
    expect(GET).toHaveBeenCalledTimes(1)
  })

  it('sets error when the API returns an error', async () => {
    GET.mockResolvedValue({ data: undefined, error: { detail: 'down' } })
    const state = usePlaybooks()
    await flushPromises()
    expect(state.error.value).toBe(true)
    expect(state.playbooks.value).toEqual([])
  })

  it('sets error when fetching throws', async () => {
    GET.mockRejectedValue(new Error('down'))
    const state = usePlaybooks()
    await flushPromises()
    expect(state.error.value).toBe(true)
  })

  it('deduplicates concurrent calls and overlapping reloads', async () => {
    let resolve: ((value: unknown) => void) | undefined
    GET.mockImplementationOnce(
      () =>
        new Promise((result) => {
          resolve = result
        }),
    ).mockResolvedValueOnce({
      data: [{ id: 'pb-2', title: 'Deploy' }],
      error: undefined,
    })
    const first = usePlaybooks()
    const second = usePlaybooks()
    expect(GET).toHaveBeenCalledTimes(1)
    resolve?.({ data: [{ id: 'pb-1', title: 'Triage' }], error: undefined })
    await flushPromises()
    expect(first.playbooks.value).toEqual([{ id: 'pb-1', title: 'Triage' }])
    expect(second.playbooks.value).toEqual(first.playbooks.value)
    const firstReload = first.reload()
    const secondReload = first.reload()
    await Promise.all([firstReload, secondReload])
    expect(GET).toHaveBeenCalledTimes(2)
    expect(first.playbooks.value).toEqual([{ id: 'pb-2', title: 'Deploy' }])
  })
})
