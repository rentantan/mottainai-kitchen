import { describe, expect, it } from 'vitest'
import type { PantryItem } from './types'
import { dateOffset } from './data'
import { daysUntil, expiryClass, expiryText, formatQuantity, getFallbackSuggestions, guessAmount, nameMatches, normalize, pantryMatchesFor } from './utils'

const item = (name: string, days: number, extra: Partial<PantryItem> = {}): PantryItem => ({
  id: name, name, quantity: 1, unit: '個', expiryDate: dateOffset(days), category: 'その他', emoji: '🛒', note: '', createdAt: '', ...extra,
})

describe('normalize', () => {
  it('folds katakana, width and spaces', () => {
    expect(normalize('ネギ')).toBe('ねぎ')
    expect(normalize('ｽﾊﾟｹﾞｯﾃｨ')).toBe('すぱげってぃ')
    expect(normalize('絹　豆腐')).toBe('絹豆腐')
  })
})

describe('nameMatches', () => {
  it.each([
    ['鶏肉', '鶏もも肉'], ['ねぎ', 'ネギ'], ['しょうゆ', '醤油'], ['ごはん', 'ご飯'],
    ['卵', 'たまご'], ['トマト', 'ミニトマト'], ['うどん', '冷凍うどん'], ['ツナ缶', 'シーチキン'],
  ])('%s ≒ %s', (a, b) => {
    expect(nameMatches(a, b)).toBe(true)
    expect(nameMatches(b, a)).toBe(true)
  })
  it.each([['鶏肉', '豚肉'], ['玉ねぎ', 'にんじん'], ['', '卵']])('%s ≠ %s', (a, b) => {
    expect(nameMatches(a, b)).toBe(false)
  })
})

describe('guessAmount', () => {
  it('reads amounts in the pantry unit', () => {
    expect(guessAmount('鶏肉 120g', 'g')).toBe(120)
    expect(guessAmount('豆腐 1/2丁', '丁')).toBe(0.5)
    expect(guessAmount('卵 1個', '個')).toBe(1)
  })
  it('returns null when units differ', () => {
    expect(guessAmount('牛乳 150ml', '本')).toBeNull()
    expect(guessAmount('塩こしょう 少々', 'g')).toBeNull()
  })
})

describe('expiry helpers', () => {
  it('counts days from today', () => {
    expect(daysUntil(dateOffset(0))).toBe(0)
    expect(daysUntil(dateOffset(3))).toBe(3)
    expect(daysUntil(dateOffset(-2))).toBe(-2)
  })
  it('labels and classifies', () => {
    expect(expiryText(-2)).toBe('2日超過')
    expect(expiryText(0)).toBe('今日まで')
    expect(expiryText(1)).toBe('明日まで')
    expect(expiryText(5)).toBe('あと5日')
    expect([-1, 1, 3, 4].map(expiryClass)).toEqual(['expired', 'urgent', 'soon', 'fresh'])
  })
})

describe('formatQuantity', () => {
  it('drops needless decimals', () => {
    expect(formatQuantity(2)).toBe('2')
    expect(formatQuantity(1 / 3)).toBe('0.33')
  })
})

describe('pantryMatchesFor', () => {
  it('skips expired stock and returns the nearest expiry first', () => {
    const pantry = [item('卵', 5, { id: 'late' }), item('たまご', 1, { id: 'soon' }), item('玉子', -1, { id: 'expired' })]
    expect(pantryMatchesFor('卵', pantry).map((row) => row.id)).toEqual(['soon', 'late'])
  })
})

describe('getFallbackSuggestions', () => {
  it('puts recipes using the most urgent item first', () => {
    const pantry = [item('ほうれん草', 0, { unit: '袋' }), item('卵', 3), item('にんじん', 7, { unit: '本' })]
    const [top] = getFallbackSuggestions(pantry, ['しょうゆ'], 500, 20)
    expect(top.ingredients).toContain('ほうれん草')
    expect(top.missingIngredients).toEqual([])
  })
  it('respects budget and time', () => {
    const recipes = getFallbackSuggestions([], [], 300, 10)
    expect(recipes.length).toBeGreaterThan(0)
    expect(recipes.every((r) => r.minutes <= 10 && (r.estimatedCostYen ?? 0) <= 300)).toBe(true)
  })
  it('never counts expired items as available', () => {
    const [top] = getFallbackSuggestions([item('鶏もも肉', -1, { unit: 'g', quantity: 200 })], [], 500, 20)
    expect(top.matchedIngredients).not.toContain('鶏肉')
  })
})
