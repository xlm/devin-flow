import { startStack } from './harness/stack.js'

export default async function globalSetup() {
  const stack = await startStack()
  process.env.E2E_STUB_URL = stack.stub.url
  return stack.teardown
}
