import test from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { sensitivePaths, confirmationForRequest } from '../src/utils/sensitiveOperations.js'

test('every annotated backend operation has a confirmation path', () => {
  const actual = new Set()
  function visit(dir) {
    for (const item of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, item.name)
      if (item.isDirectory() && !['target', '.cache', '.venv', 'node_modules'].includes(item.name)) visit(path)
      else if (item.isFile() && item.name.endsWith('Controller.java')) {
        const source = readFileSync(path, 'utf8')
        const base = source.match(/@RequestMapping\("([^"]+)"\)/)?.[1]
        for (const match of source.matchAll(/@AdminSensitiveConfirm\s*@PostMapping\("([^"]+)"\)|@PostMapping\("([^"]+)"\)\s*@AdminSensitiveConfirm/g)) actual.add(base + (match[1] || match[2]))
      }
    }
  }
  visit(fileURLToPath(new URL('../../../Simlect-backend/', import.meta.url)))
  assert.equal(actual.size, 25)
  assert.deepEqual([...sensitivePaths].sort(), [...actual].sort())
})

test('merchant reply prompts for its bound operation in dev and production', async () => {
  for (const url of ['/order/bizComment', '/api/order/bizComment', '/admin-api/order/bizComment']) {
    let called = 0
    const token = await confirmationForRequest(url, undefined, async (_, path) => {
      assert.equal(path, '/admin/order/bizComment')
      called++
      return 'one-use-ticket'
    })
    assert.equal(token, 'one-use-ticket')
    assert.equal(called, 1)
  }
})

test('existing tickets and read operations do not prompt again', async () => {
  const unexpected = () => { throw Error('Unexpected password prompt') }
  assert.equal(await confirmationForRequest('/order/delivery', 'existing-ticket', unexpected), 'existing-ticket')
  assert.equal(await confirmationForRequest('/order/getComment', undefined, unexpected), undefined)
})

test('cancel and failed password exchange stop before a business request', async () => {
  for (const error of ['cancel', Error('Wrong password')]) {
    let submitted = false
    try {
      await confirmationForRequest('/order/bizComment', undefined, async () => { throw error })
      submitted = true
    } catch (caught) { assert.equal(caught, error) }
    assert.equal(submitted, false)
  }
})
