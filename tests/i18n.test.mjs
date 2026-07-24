import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
// The release workflow uses Node's built-in runner so this check adds no package dependency.
// eslint-disable-next-line test/no-import-node-test
import test from 'node:test'

import { HUD_TEMPLATES } from '../packages/shared/src/config/hud.ts'
import { DRIVE_MODES } from '../packages/shared/src/config/modes.ts'
import {
  CLUTCH_ASSIST_FIELDS,
  CLUTCH_TIMING_SLIDERS,
  FEATURE_TOGGLES,
  HOTKEY_FIELDS,
  LOG_OUTPUT_FORMAT_OPTIONS,
  OUTPUT_MODE_OPTIONS,
  REV_BLIP_FIELDS,
  REV_BLIP_TIMING_SLIDERS,
  SETTING_GROUPS,
  SETTING_SLIDERS,
  SHIFT_KEY_FIELDS,
  THROTTLE_KEY_FIELDS,
  VJOY_SHIFT_BUTTON_FIELDS,
} from '../packages/shared/src/config/settings.ts'
import en from '../packages/shared/src/locales/en.ts'
import zhCN from '../packages/shared/src/locales/zh-CN.ts'

function flattenKeys(value, prefix = '', keys = new Set()) {
  for (const [key, child] of Object.entries(value)) {
    const fullKey = prefix ? `${prefix}.${key}` : key
    if (child && typeof child === 'object') flattenKeys(child, fullKey, keys)
    else keys.add(fullKey)
  }
  return keys
}

function sourceFiles(directory, files = []) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name)
    if (entry.isDirectory()) sourceFiles(path, files)
    else if (/\.(?:ts|vue)$/.test(entry.name)) files.push(path)
  }
  return files
}

function staticTranslationKeys() {
  const keys = new Set()
  const callPattern =
    /(?<![\w$])(?:\$t|t)\(\s*['"]([A-Za-z][\w-]*(?:\.[\w-]+)+)['"]/g

  for (const root of ['apps', 'packages']) {
    for (const file of sourceFiles(root)) {
      const source = readFileSync(file, 'utf8')
      for (const match of source.matchAll(callPattern)) keys.add(match[1])
    }
  }
  return keys
}

function dynamicTranslationKeys() {
  const keys = new Set(staticTranslationKeys())
  const add = (key) => keys.add(key)

  for (const item of FEATURE_TOGGLES) {
    add(`settings.${item.i18nKey}`)
    add(`settings.hints.${item.hintKey}`)
  }
  for (const item of SETTING_SLIDERS) add(`settings.${item.i18nKey}`)

  const extrasCollections = [
    HOTKEY_FIELDS,
    SHIFT_KEY_FIELDS,
    THROTTLE_KEY_FIELDS,
    CLUTCH_ASSIST_FIELDS,
    REV_BLIP_FIELDS,
    CLUTCH_TIMING_SLIDERS,
    REV_BLIP_TIMING_SLIDERS,
    OUTPUT_MODE_OPTIONS,
    VJOY_SHIFT_BUTTON_FIELDS,
  ]
  for (const collection of extrasCollections) {
    for (const item of collection) add(`extras.${item.i18nKey}`)
  }

  for (const item of LOG_OUTPUT_FORMAT_OPTIONS) add(`logger.${item.i18nKey}`)
  for (const item of SETTING_GROUPS) add(`settings.${item.i18nKey}`)
  for (const item of HUD_TEMPLATES) add(`electronApp.${item.i18nKey}`)
  for (const item of DRIVE_MODES) {
    add(`modes.${item.i18nKey}.name`)
    add(`modes.${item.i18nKey}.tag`)
  }
  add('locale.en')
  add('locale.zh')
  return keys
}

test('English and Chinese locale trees have matching keys', () => {
  assert.deepEqual([...flattenKeys(en)].sort(), [...flattenKeys(zhCN)].sort())
})

test('every UI translation reference resolves in both locales', () => {
  const required = dynamicTranslationKeys()
  for (const [name, locale] of [
    ['en', en],
    ['zh-CN', zhCN],
  ]) {
    const available = flattenKeys(locale)
    const missing = [...required].filter((key) => !available.has(key)).sort()
    assert.deepEqual(missing, [], `${name} is missing: ${missing.join(', ')}`)
  }
})
