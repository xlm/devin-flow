import { computed, onMounted, onUnmounted, ref, watchEffect } from 'vue'
import { Moon, Sun, SunMoon } from '@lucide/vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'theme'
const MODES: ThemeMode[] = ['light', 'dark', 'system']
const ICONS = { light: Sun, dark: Moon, system: SunMoon }
const DARK_QUERY = '(prefers-color-scheme: dark)'

function isThemeMode(value: string | null): value is ThemeMode {
  return MODES.some((mode) => mode === value)
}

function readStoredMode(): ThemeMode {
  const stored = localStorage.getItem(STORAGE_KEY)
  return isThemeMode(stored) ? stored : 'system'
}

export function useTheme() {
  const mode = ref<ThemeMode>(readStoredMode())
  const media = window.matchMedia(DARK_QUERY)
  const systemDark = ref(media.matches)

  const isDark = computed(() =>
    mode.value === 'system' ? systemDark.value : mode.value === 'dark',
  )
  const icon = computed(() => ICONS[mode.value])

  function cycleMode() {
    mode.value = MODES[(MODES.indexOf(mode.value) + 1) % MODES.length]!
    localStorage.setItem(STORAGE_KEY, mode.value)
  }

  function onSystemChange(event: MediaQueryListEvent) {
    systemDark.value = event.matches
  }

  watchEffect(() => {
    document.documentElement.classList.toggle('dark', isDark.value)
  })

  onMounted(() => media.addEventListener('change', onSystemChange))
  onUnmounted(() => media.removeEventListener('change', onSystemChange))

  return { mode, isDark, icon, cycleMode }
}
