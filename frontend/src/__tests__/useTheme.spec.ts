import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'
import { Moon, Sun, SunMoon } from '@lucide/vue'
import { useTheme } from '@/composables/useTheme'

type Listener = (event: MediaQueryListEvent) => void

const media = {
  matches: false,
  listeners: new Set<Listener>(),
  addEventListener: vi.fn((_: 'change', fn: Listener) =>
    media.listeners.add(fn),
  ),
  removeEventListener: vi.fn((_: 'change', fn: Listener) =>
    media.listeners.delete(fn),
  ),
  emit(matches: boolean) {
    media.listeners.forEach((fn) => fn({ matches } as MediaQueryListEvent))
  },
}

function mountTheme() {
  let theme!: ReturnType<typeof useTheme>
  const wrapper = mount(
    defineComponent({
      setup() {
        theme = useTheme()
        return () => h('div')
      },
    }),
  )
  return { wrapper, theme }
}

const hasDarkClass = () => document.documentElement.classList.contains('dark')

describe('useTheme', () => {
  beforeEach(() => {
    media.matches = false
    media.listeners.clear()
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue(media))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('defaults to system mode and follows the OS preference', async () => {
    media.matches = true
    const { theme } = mountTheme()
    expect(theme.mode.value).toBe('system')
    expect(theme.icon.value).toBe(SunMoon)
    expect(hasDarkClass()).toBe(true)

    media.emit(false)
    await nextTick()
    expect(hasDarkClass()).toBe(false)
  })

  it('restores a stored mode and ignores unknown values', () => {
    localStorage.setItem('theme', 'dark')
    expect(mountTheme().theme.mode.value).toBe('dark')

    localStorage.setItem('theme', 'bogus')
    expect(mountTheme().theme.mode.value).toBe('system')
  })

  it('cycles light -> dark -> system, persisting and applying each', async () => {
    localStorage.setItem('theme', 'light')
    const { theme } = mountTheme()
    expect(theme.icon.value).toBe(Sun)
    expect(hasDarkClass()).toBe(false)

    theme.cycleMode()
    await nextTick()
    expect(theme.mode.value).toBe('dark')
    expect(theme.icon.value).toBe(Moon)
    expect(localStorage.getItem('theme')).toBe('dark')
    expect(hasDarkClass()).toBe(true)

    theme.cycleMode()
    await nextTick()
    expect(theme.mode.value).toBe('system')
    expect(hasDarkClass()).toBe(false)

    theme.cycleMode()
    expect(theme.mode.value).toBe('light')
  })

  it('falls back to system mode and keeps working when storage is blocked', () => {
    const blocked = () => {
      throw new DOMException('blocked', 'SecurityError')
    }
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(blocked)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(blocked)

    const { theme } = mountTheme()
    expect(theme.mode.value).toBe('system')
    theme.cycleMode()
    expect(theme.mode.value).toBe('light')

    vi.restoreAllMocks()
  })

  it('stops following the OS preference after unmount', () => {
    const { wrapper } = mountTheme()
    expect(media.listeners.size).toBe(1)
    wrapper.unmount()
    expect(media.listeners.size).toBe(0)
  })
})
