import { describe, expect, it } from 'vitest'

import { sessionStatusBadgeClass } from '@/lib/sessionStatus'

describe('sessionStatusBadgeClass', () => {
  it.each([
    ['running', 'bg-blue-500'],
    ['claimed', 'bg-blue-500'],
    ['resuming', 'bg-blue-500'],
    ['exit', 'bg-green-500'],
    ['error', 'bg-destructive'],
    ['new', 'bg-muted-foreground'],
    ['suspended', 'bg-muted-foreground'],
    ['weird', 'bg-muted-foreground'],
  ])('maps %s to %s', (status, expected) => {
    expect(sessionStatusBadgeClass(status)).toBe(expected)
  })
})
