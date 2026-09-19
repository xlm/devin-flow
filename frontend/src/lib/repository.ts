export const REPOSITORY_FULL_NAME_PATTERN =
  /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\/(?!\.{1,2}$)[A-Za-z0-9._-]{1,100}$/

export function isRepositoryFullName(value: string): boolean {
  return REPOSITORY_FULL_NAME_PATTERN.test(value)
}
