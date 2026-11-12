import { describe, expect, it } from 'vitest'
import { findFoodPreset } from './foodPresets'

describe('findFoodPreset', () => {
  it('guesses common groceries', () => {
    expect(findFoodPreset('牛乳')).toMatchObject({ category: '乳製品・卵', unit: '本' })
    expect(findFoodPreset('鶏むね肉')).toMatchObject({ category: '肉・魚', unit: 'g' })
    expect(findFoodPreset('もやし')).toMatchObject({ unit: '袋', days: 2 })
  })
  it('prefers the more specific keyword', () => {
    expect(findFoodPreset('玉ねぎ')?.emoji).toBe('🧅')
    expect(findFoodPreset('長ねぎ')?.emoji).toBe('🌿')
    expect(findFoodPreset('ミニトマト')?.unit).toBe('パック')
    expect(findFoodPreset('鶏卵')?.category).toBe('乳製品・卵')
    expect(findFoodPreset('冷凍うどん')?.days).toBe(60)
  })
  it('ignores katakana/hiragana differences', () => {
    expect(findFoodPreset('タマゴ')?.category).toBe('乳製品・卵')
  })
  it('returns null for unknown or empty names', () => {
    expect(findFoodPreset('')).toBeNull()
    expect(findFoodPreset('謎の食材')).toBeNull()
  })
})
