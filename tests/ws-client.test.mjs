import assert from 'node:assert/strict'
// eslint-disable-next-line test/no-import-node-test
import test from 'node:test'

import { TcuWsClient } from '../packages/shared/src/api/ws-client.ts'

class FakeWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 3
  static instances = []

  constructor(url) {
    this.url = url
    this.readyState = FakeWebSocket.CONNECTING
    FakeWebSocket.instances.push(this)
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  init() {
    this.onmessage?.({ data: JSON.stringify({ type: 'init', data: {} }) })
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED
  }

  emitClose() {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.()
  }

  send() {}
}

test('a stale socket close cannot disconnect a replacement socket', () => {
  const originalWebSocket = globalThis.WebSocket
  globalThis.WebSocket = FakeWebSocket
  FakeWebSocket.instances = []

  try {
    const states = []
    const client = new TcuWsClient('ws://127.0.0.1:8765/ws')
    client.onConnectionChange((open) => states.push(open))
    client.connect()

    const oldSocket = FakeWebSocket.instances[0]
    client.setUrl('ws://127.0.0.1:8877/ws')
    const newSocket = FakeWebSocket.instances[1]
    newSocket.open()
    newSocket.init()

    assert.equal(client.connected, true)
    oldSocket.emitClose()
    assert.equal(client.connected, true)
    assert.deepEqual(states, [true])
    client.disconnect()
  } finally {
    globalThis.WebSocket = originalWebSocket
  }
})
