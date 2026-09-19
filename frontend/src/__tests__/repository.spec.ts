import { describe, expect, it } from 'vitest'
import {
  isRepositoryFullName,
  REPOSITORY_FULL_NAME_PATTERN,
} from '@/lib/repository'

describe('repository names', () => {
  it.each([
    'octo/repo',
    'octo-org/my.repo_name-1',
    'a/b',
    `${'a'.repeat(39)}/repo`,
  ])('accepts valid name %s', (value) => {
    expect(isRepositoryFullName(value)).toBe(true)
  })

  it.each([
    'octo',
    'octo/',
    '/repo',
    'octo/repo/extra',
    '-octo/repo',
    'octo-/repo',
    'octo/.',
    'octo/..',
    'octo/re po',
    'octo/re;po',
    'Ｏcto/repo',
    'octo/répo',
    'octo//repo',
    'octo\\repo',
    'octo/repo\n',
    `${'a'.repeat(40)}/repo`,
    `octo/${'r'.repeat(101)}`,
  ])('rejects invalid name %s', (value) => {
    expect(isRepositoryFullName(value)).toBe(false)
  })

  it('exports the repository pattern', () => {
    expect(REPOSITORY_FULL_NAME_PATTERN.test('octo/repo')).toBe(true)
  })
})
