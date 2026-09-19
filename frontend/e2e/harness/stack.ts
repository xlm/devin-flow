import { execFile, spawn, type ChildProcess } from 'node:child_process'
import { createWriteStream } from 'node:fs'
import { mkdir } from 'node:fs/promises'
import net from 'node:net'
import path from 'node:path'
import { promisify } from 'node:util'
import { startStub, type StubDevin } from './stub-devin.js'

const execFileAsync = promisify(execFile)
const FAKE_TOKEN = 'e2e-fake-token'
const FAKE_ORG = 'e2e-org'

type Stack = {
  teardown: () => Promise<void>
  stub: StubDevin
}

function repoRoot(): string {
  return (
    process.env.E2E_REPO_ROOT ?? path.resolve(import.meta.dirname, '../../..')
  )
}

function envFor(databaseUrl: string, stubUrl: string): NodeJS.ProcessEnv {
  const env = { ...process.env }
  for (const key of Object.keys(env)) {
    if (key.startsWith('DEVIN_')) delete env[key]
  }
  env.DATABASE_URL = databaseUrl
  env.DEVIN_API_TOKEN = FAKE_TOKEN
  env.DEVIN_ORG_ID = FAKE_ORG
  env.DEVIN_API_BASE_URL = `${stubUrl}/v3`
  env.POLL_INTERVAL_SECONDS = '0'
  return env
}

async function portIsFree(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = net.createServer()
    server.once('error', () => resolve(false))
    server.listen(port, '127.0.0.1', () => {
      server.close(() => resolve(true))
    })
  })
}

async function waitForPort(port: number, open: boolean): Promise<void> {
  const deadline = Date.now() + 60_000
  while (Date.now() < deadline) {
    const listening = await new Promise<boolean>((resolve) => {
      const socket = net.createConnection({ host: '127.0.0.1', port })
      socket.once('connect', () => {
        socket.destroy()
        resolve(true)
      })
      socket.once('error', () => resolve(false))
    })
    if (listening === open) return
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error(
    `timed out waiting for port ${port} to be ${open ? 'open' : 'closed'}`,
  )
}

async function waitForUrl(url: string): Promise<void> {
  const deadline = Date.now() + 60_000
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url)
      if (response.ok) return
    } catch {
      // The child process is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error(`timed out waiting for ${url}`)
}

async function waitForPostgres(container: string): Promise<void> {
  const deadline = Date.now() + 60_000
  while (Date.now() < deadline) {
    try {
      await execFileAsync('docker', [
        'exec',
        container,
        'pg_isready',
        '-U',
        'devin',
        '-d',
        'devin_flow',
      ])
      return
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
  }
  throw new Error('timed out waiting for Postgres to accept connections')
}

function spawnLogged(
  command: string,
  args: string[],
  cwd: string,
  env: NodeJS.ProcessEnv,
  logPath: string,
): ChildProcess {
  const log = createWriteStream(logPath, { flags: 'a' })
  const child = spawn(command, args, {
    cwd,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  child.stdout?.pipe(log, { end: false })
  child.stderr?.pipe(log, { end: false })
  child.once('close', () => log.end())
  return child
}

async function stopProcess(child: ChildProcess | undefined): Promise<void> {
  if (!child || child.exitCode !== null) return
  child.kill('SIGTERM')
  await new Promise<void>((resolve) => {
    const timer = setTimeout(() => {
      child.kill('SIGKILL')
      resolve()
    }, 5_000)
    child.once('exit', () => {
      clearTimeout(timer)
      resolve()
    })
  })
}

export async function startStack(): Promise<Stack> {
  const root = repoRoot()
  const results = path.join(root, 'frontend', 'test-results', 'stack')
  await mkdir(results, { recursive: true })
  if (!(await portIsFree(8000)) || !(await portIsFree(5174))) {
    throw new Error('E2E preflight failed: ports 8000 and 5174 must be free')
  }
  try {
    await execFileAsync('docker', ['version'])
  } catch (error) {
    throw new Error(
      `E2E preflight failed: Docker is required (${String(error)})`,
    )
  }

  const { stdout: containerId } = await execFileAsync('docker', [
    'run',
    '-d',
    '--rm',
    '-P',
    '-e',
    'POSTGRES_USER=devin',
    '-e',
    'POSTGRES_PASSWORD=devin',
    '-e',
    'POSTGRES_DB=devin_flow',
    'postgres:18',
  ])
  const container = containerId.trim()
  let backend: ChildProcess | undefined
  let vite: ChildProcess | undefined
  let stub: StubDevin | undefined
  let databaseUrl = ''
  try {
    const { stdout: mapped } = await execFileAsync('docker', [
      'port',
      container,
      '5432',
    ])
    const port = Number.parseInt(mapped.trim().split(':').pop() ?? '', 10)
    if (!Number.isInteger(port))
      throw new Error(`could not resolve Postgres port: ${mapped}`)
    await waitForPostgres(container)
    databaseUrl = `postgresql+psycopg://devin:devin@127.0.0.1:${port}/devin_flow`
    stub = await startStub({
      dbReset: async () => {
        await execFileAsync('docker', [
          'exec',
          container,
          'psql',
          '-U',
          'devin',
          '-d',
          'devin_flow',
          '-c',
          'TRUNCATE invocation, poller_state, edge, action_node, trigger_node, outcome_node CASCADE',
        ])
      },
    })
    const stubUrl = stub.url
    const baseUrl = `${stubUrl}/v3`
    if (
      new URL(baseUrl).hostname !== '127.0.0.1' ||
      FAKE_TOKEN !== 'e2e-fake-token'
    ) {
      throw new Error('E2E safety check failed: upstream is not the local stub')
    }
    const env = envFor(databaseUrl, stubUrl)
    await execFileAsync(
      'uv',
      ['run', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', 'head'],
      {
        cwd: root,
        env,
      },
    )
    backend = spawnLogged(
      'uv',
      [
        'run',
        'uvicorn',
        'devin_flow.main:app',
        '--host',
        '127.0.0.1',
        '--port',
        '8000',
      ],
      root,
      env,
      path.join(results, 'backend.log'),
    )
    await waitForUrl('http://127.0.0.1:8000/api/health')
    vite = spawnLogged(
      'pnpm',
      ['exec', 'vite', '--host', '127.0.0.1', '--port', '5174', '--strictPort'],
      path.join(root, 'frontend'),
      env,
      path.join(results, 'vite.log'),
    )
    await waitForUrl('http://127.0.0.1:5174')
    const stackStub = stub
    stackStub.configureBackend({
      stop: async () => {
        await stopProcess(backend)
        await waitForPort(8000, false)
      },
      start: async () => {
        if (!backend || backend.exitCode !== null) {
          backend = spawnLogged(
            'uv',
            [
              'run',
              'uvicorn',
              'devin_flow.main:app',
              '--host',
              '127.0.0.1',
              '--port',
              '8000',
            ],
            root,
            env,
            path.join(results, 'backend.log'),
          )
        }
        await waitForUrl('http://127.0.0.1:8000/api/health')
      },
    })
    return {
      stub: stackStub,
      teardown: async () => {
        await stopProcess(vite)
        await stopProcess(backend)
        await stackStub.close()
        await execFileAsync('docker', ['rm', '-f', container]).catch(
          () => undefined,
        )
      },
    }
  } catch (error) {
    await stopProcess(vite)
    await stopProcess(backend)
    await stub?.close()
    await execFileAsync('docker', ['rm', '-f', container]).catch(
      () => undefined,
    )
    throw error
  }
}
