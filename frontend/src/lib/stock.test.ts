import { afterEach, describe, expect, it, vi } from 'vitest'
import type { PantryItem } from '../types'
import { dateOffset } from './dates'
import { stockText } from './format'
import { restockCandidates, sameFoodInPantry } from './ingredients'
import { loadPreferences } from '../hooks/useRecipes'

const item = (name: string, days: number, extra: Partial<PantryItem> = {}): PantryItem => ({
  id: `${name}-${days}`, name, quantity: 1, unit: '個', expiryDate: dateOffset(days), category: 'その他', emoji: '🛒', note: '', createdAt: '', ...extra,
})

describe('sameFoodInPantry', () => {
  it('finds other spellings, expired ones included, oldest first', () => {
    const pantry = [item('たまご', 5), item('卵', -1), item('牛乳', 2)]
    expect(sameFoodInPantry('卵', pantry).map((row) => row.id)).toEqual(['卵--1', 'たまご-5'])
  })
  it('keeps different foods apart and ignores an empty name', () => {
    const pantry = [item('玉ねぎ', 3), item('醤油', 30)]
    expect(sameFoodInPantry('ねぎ', pantry)).toEqual([])
    expect(sameFoodInPantry('油', pantry)).toEqual([])
    expect(sameFoodInPantry('  ', pantry)).toEqual([])
  })
})

describe('stockText', () => {
  it('shows what is left and how long it keeps', () => {
    expect(stockText(item('卵', 3, { quantity: 6 }))).toBe('卵 残り6個・あと3日')
    expect(stockText(item('ごはん', 20, { frozen: true, quantity: 2, unit: '杯' }))).toBe('❄️ごはん 残り2杯・あと20日')
  })
})

describe('restockCandidates', () => {
  it('drops foods still in the fridge or already on the list', () => {
    const pantry = [item('たまご', 3), item('牛乳', -2)]
    // 卵 is in stock; 牛乳 is only expired, so it is worth buying; ネギ is already on the list as 長ねぎ.
    expect(restockCandidates(['卵', '牛乳', 'ネギ', '納豆'], pantry, ['長ねぎ'])).toEqual(['牛乳', '納豆'])
  })
})

describe('loadPreferences', () => {
  afterEach(() => vi.unstubAllGlobals())
  const stubStorage = (value: string | null) => vi.stubGlobal('localStorage', { getItem: () => value })

  it('restores the last conditions', () => {
    stubStorage(JSON.stringify({ budgetYen: 300, maxMinutes: 10, equipment: 'microwave' }))
    expect(loadPreferences('a@example.com')).toEqual({ budgetYen: 300, maxMinutes: 10, equipment: 'microwave' })
  })
  it('falls back to the defaults for missing, unknown or broken values', () => {
    stubStorage(JSON.stringify({ budgetYen: 999, equipment: 'oven' }))
    expect(loadPreferences('a@example.com')).toEqual({ budgetYen: 500, maxMinutes: 20, equipment: 'any' })
    stubStorage('{broken')
    expect(loadPreferences('a@example.com')).toEqual({ budgetYen: 500, maxMinutes: 20, equipment: 'any' })
    stubStorage(null)
    expect(loadPreferences('a@example.com')).toEqual({ budgetYen: 500, maxMinutes: 20, equipment: 'any' })
  })
})
