import { describe, expect, it } from 'vitest'

import { formatDateTime, formatNumber, resolveLocale } from './localeFormat'

describe('localeFormat', () => {
  it('normalizes supported locales', () => {
    expect(resolveLocale('zh-CN')).toBe('zh-CN')
    expect(resolveLocale('zh-TW')).toBe('zh-CN')
    expect(resolveLocale('en-US')).toBe('en-US')
    expect(resolveLocale('fr-FR')).toBe('en-US')
  })

  it('formats numbers by locale', () => {
    expect(formatNumber(1234.5, 'en-US')).toBe('1,234.5')
    expect(formatNumber(1234.5, 'zh-CN')).toBe('1,234.5')
  })

  it('formats date time with the requested locale', () => {
    const value = '2026-04-04T12:34:56Z'
    expect(formatDateTime(value, 'en-US')).toContain('2026')
    expect(formatDateTime(value, 'zh-CN')).toContain('2026')
  })
})
