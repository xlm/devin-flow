import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { client } from '@/api/client'
import { useInvocationList } from '@/composables/useInvocationList'

vi.mock('@/api/client', () => ({
  client: {
    POST: vi.fn(),
  },
}))

const post = vi.mocked(client.POST)

function mountList(
  fetcher: () => Promise<{ data?: string[]; error?: unknown }>,
) {
  let list: ReturnType<typeof useInvocationList<string>> | undefined
  const wrapper = mount(
    defineComponent({
      setup() {
        list = useInvocationList(fetcher)
        return () => h('div')
      },
    }),
  )
  return { wrapper, list: list! }
}

describe('useInvocationList archive', () => {
  beforeEach(() => {
    post.mockReset()
  })

  it('archives an invocation and reloads the list', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce({ data: ['one'] })
      .mockResolvedValueOnce({ data: [] })
    post.mockResolvedValue({ data: undefined, error: undefined })
    const { wrapper, list } = mountList(fetcher)
    await list.load()
    await expect(list.archive('inv-1')).resolves.toBe(true)
    expect(post).toHaveBeenCalledWith(
      '/api/invocations/{invocation_id}/archive',
      { params: { path: { invocation_id: 'inv-1' } } },
    )
    expect(list.items.value).toEqual([])
    expect(list.archivingIds.value).not.toContain('inv-1')
    wrapper.unmount()
  })

  it('records a failed archive', async () => {
    post.mockResolvedValue({ data: undefined, error: { detail: 'failed' } })
    const { wrapper, list } = mountList(vi.fn().mockResolvedValue({ data: [] }))
    await expect(list.archive('inv-1')).resolves.toBe(false)
    expect(list.archiveErrors.value).toContain('inv-1')
    expect(list.archivingIds.value).not.toContain('inv-1')
    wrapper.unmount()
  })

  it('records a thrown archive failure', async () => {
    post.mockRejectedValue(new Error('down'))
    const { wrapper, list } = mountList(vi.fn().mockResolvedValue({ data: [] }))
    await expect(list.archive('inv-1')).resolves.toBe(false)
    expect(list.archiveErrors.value).toContain('inv-1')
    wrapper.unmount()
  })
})
