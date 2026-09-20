const inProgress = 'bg-blue-500'
const statusClasses: Record<string, string> = {
  running: inProgress,
  claimed: inProgress,
  resuming: inProgress,
  exit: 'bg-green-500',
  error: 'bg-destructive',
}

export function sessionStatusBadgeClass(status: string): string {
  return statusClasses[status] ?? 'bg-muted-foreground'
}
