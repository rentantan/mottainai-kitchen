import { describe, expect, it } from 'vitest'
import { describeDetail } from './api'

describe('describeDetail', () => {
  it('passes through string details', () => {
    expect(describeDetail('食材が見つかりません', 'fallback')).toBe('食材が見つかりません')
  })
  it('turns validation errors into a field-specific Japanese message', () => {
    expect(describeDetail([{ loc: ['body', 'quantity'], msg: 'too small' }], 'fallback')).toBe('残量の入力内容を確認してください。')
    expect(describeDetail([{ loc: ['body', 'unknown'] }], 'fallback')).toBe('入力内容を確認してください。')
  })
  it('uses the fallback otherwise', () => {
    expect(describeDetail(undefined, 'fallback')).toBe('fallback')
  })
})
