import {
  createServer,
  type IncomingMessage,
  type ServerResponse,
} from 'node:http'
import { URL } from 'node:url'

export type StubSession = {
  session_id: string
  status: string
  title?: string | null
  url?: string | null
  automation_id?: string | null
  pull_requests?: Array<{ pr_url: string; pr_state?: string | null }>
  structured_output?: Record<string, unknown> | null
  created_at?: number | null
  updated_at?: number | null
}

export type StubCall = {
  method: string
  path: string
  query: Record<string, string | string[]>
  body: unknown
}

type Automation = {
  automation_id: string
  name: string
  enabled: boolean
  metadata: Record<string, string>
  [key: string]: unknown
}

type BackendControls = {
  stop: () => Promise<void>
  start: () => Promise<void>
}

type StubOptions = {
  dbReset: () => Promise<void>
}

function json(response: ServerResponse, status: number, value: unknown): void {
  const payload = JSON.stringify(value)
  response.writeHead(status, {
    'content-type': 'application/json',
    'content-length': Buffer.byteLength(payload),
  })
  response.end(payload)
}

async function requestBody(request: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = []
  for await (const chunk of request) chunks.push(Buffer.from(chunk))
  if (!chunks.length) return undefined
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}

function queryObject(url: URL): Record<string, string | string[]> {
  const result: Record<string, string | string[]> = {}
  for (const key of new Set(url.searchParams.keys())) {
    const values = url.searchParams.getAll(key)
    result[key] = values.length === 1 ? values[0] : values
  }
  return result
}

export class StubDevin {
  readonly calls: StubCall[] = []
  private readonly server = createServer(
    (request, response) => void this.handle(request, response),
  )
  private readonly automations: Automation[] = []
  private sessions: StubSession[] = []
  private backendControls: BackendControls | undefined
  private nextAutomation = 1

  constructor(private readonly options: StubOptions) {}

  get url(): string {
    const address = this.server.address()
    if (!address || typeof address === 'string') {
      throw new Error('stub Devin server is not listening')
    }
    return `http://127.0.0.1:${address.port}`
  }

  async start(): Promise<void> {
    await new Promise<void>((resolve, reject) => {
      this.server.once('error', reject)
      this.server.listen(0, '127.0.0.1', () => {
        this.server.removeListener('error', reject)
        resolve()
      })
    })
  }

  async close(): Promise<void> {
    if (!this.server.listening) return
    await new Promise<void>((resolve, reject) =>
      this.server.close((error) => (error ? reject(error) : resolve())),
    )
  }

  configureBackend(controls: BackendControls): void {
    this.backendControls = controls
  }

  reset(): void {
    this.calls.length = 0
    this.automations.length = 0
    this.sessions = []
    this.nextAutomation = 1
  }

  setSessions(sessions: StubSession[]): void {
    this.sessions = sessions
  }

  private async handle(
    request: IncomingMessage,
    response: ServerResponse,
  ): Promise<void> {
    const url = new URL(request.url ?? '/', this.url)
    const body = await requestBody(request)
    this.calls.push({
      method: request.method ?? 'GET',
      path: url.pathname,
      query: queryObject(url),
      body,
    })

    if (url.pathname === '/_harness/calls' && request.method === 'GET') {
      json(response, 200, this.calls)
      return
    }
    if (url.pathname === '/_harness/reset' && request.method === 'POST') {
      this.reset()
      json(response, 200, { ok: true })
      return
    }
    if (url.pathname === '/_harness/sessions' && request.method === 'PUT') {
      this.setSessions(Array.isArray(body) ? (body as StubSession[]) : [])
      json(response, 200, { ok: true })
      return
    }
    if (url.pathname === '/_harness/db/reset' && request.method === 'POST') {
      await this.options.dbReset()
      json(response, 200, { ok: true })
      return
    }
    if (
      url.pathname === '/_harness/backend/stop' &&
      request.method === 'POST'
    ) {
      await this.backendControls?.stop()
      json(response, 200, { ok: true })
      return
    }
    if (
      url.pathname === '/_harness/backend/start' &&
      request.method === 'POST'
    ) {
      await this.backendControls?.start()
      json(response, 200, { ok: true })
      return
    }

    const playbooks = /^\/v3\/organizations\/[^/]+\/playbooks$/
    const repositories = /^\/v3beta1\/organizations\/[^/]+\/repositories$/
    const automations = /^\/v3\/organizations\/[^/]+\/automations$/
    const automation = /^\/v3\/organizations\/[^/]+\/automations\/([^/]+)$/
    const sessions = /^\/v3\/organizations\/[^/]+\/sessions$/
    const session = /^\/v3\/organizations\/[^/]+\/sessions\/([^/]+)$/

    if (playbooks.test(url.pathname) && request.method === 'GET') {
      json(response, 200, {
        items: [
          {
            playbook_id: 'pb-triage',
            title: 'Issue triage',
            body: 'Triage the issue.',
          },
        ],
        has_next_page: false,
      })
      return
    }
    if (repositories.test(url.pathname) && request.method === 'GET') {
      json(response, 200, {
        items: [{ repo_path: 'acme/widgets', repo_name: 'widgets' }],
        has_next_page: false,
      })
      return
    }
    if (automations.test(url.pathname) && request.method === 'GET') {
      const metadata = Object.entries(queryObject(url))
        .filter(([key]) => key.startsWith('metadata.'))
        .map(([key, value]) => [key.slice('metadata.'.length), value])
      const items = this.automations.filter((item) =>
        metadata.every(
          ([key, value]) =>
            typeof key === 'string' &&
            typeof value === 'string' &&
            item.metadata[key] === value,
        ),
      )
      json(response, 200, { items, has_next_page: false })
      return
    }
    if (automations.test(url.pathname) && request.method === 'POST') {
      const payload = (body ?? {}) as Record<string, unknown>
      const created: Automation = {
        ...payload,
        automation_id: `auto-${this.nextAutomation++}`,
        name: String(payload.name ?? ''),
        enabled: Boolean(payload.enabled),
        metadata: (payload.metadata ?? {}) as Record<string, string>,
      }
      this.automations.push(created)
      json(response, 201, created)
      return
    }
    if (automation.test(url.pathname) && request.method === 'PATCH') {
      const id = automation.exec(url.pathname)?.[1]
      const current = this.automations.find((item) => item.automation_id === id)
      if (!current) {
        json(response, 404, { detail: 'automation not found' })
        return
      }
      Object.assign(current, body ?? {})
      json(response, 200, current)
      return
    }
    if (sessions.test(url.pathname) && request.method === 'GET') {
      const ids = url.searchParams.getAll('automation_ids')
      json(response, 200, {
        items: this.sessions.filter((item) =>
          ids.includes(item.automation_id ?? ''),
        ),
        has_next_page: false,
      })
      return
    }
    if (session.test(url.pathname) && request.method === 'GET') {
      const id = session.exec(url.pathname)?.[1]
      const found = this.sessions.find((item) => item.session_id === id)
      if (!found) {
        json(response, 404, { detail: 'session not found' })
        return
      }
      json(response, 200, found)
      return
    }
    json(response, 404, { detail: 'unknown stub path' })
  }
}

export async function startStub(options: StubOptions): Promise<StubDevin> {
  const stub = new StubDevin(options)
  await stub.start()
  return stub
}
