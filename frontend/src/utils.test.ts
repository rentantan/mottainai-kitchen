import { describe, expect, it } from 'vitest'
import type { PantryItem, SavedRecipe } from './types'
import { dateOffset } from './data'
import { daysUntil, expiryClass, expiryText, formatQuantity, getFallbackSuggestions, guessAmount, nameMatches, normalize, pantryMatchesFor, findSaved, rankSavedRecipes, toSavedPayload } from './utils'

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
    ['鶏肉', '国産鶏もも肉'], ['ねぎ', '九条ねぎ'], ['油', 'サラダ油'], ['卵', '卵(Mサイズ)'], ['キャベツ', 'キャベツ1/2'],
  ])('%s ≒ %s', (a, b) => {
    expect(nameMatches(a, b)).toBe(true)
    expect(nameMatches(b, a)).toBe(true)
  })
  it.each([
    ['鶏肉', '豚肉'], ['玉ねぎ', 'にんじん'], ['', '卵'],
    ['ねぎ', '玉ねぎ'], ['長ねぎ', '玉ねぎ'], ['油', '醤油'], ['酢', 'ポン酢'], ['米', '米酢'], ['塩', '塩こしょう'], ['卵', '卵豆腐'],
  ])('%s ≠ %s', (a, b) => {
    expect(nameMatches(a, b)).toBe(false)
    expect(nameMatches(b, a)).toBe(false)
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
  it('only offers stove-free recipes in microwave mode', () => {
    const recipes = getFallbackSuggestions([], [], 700, 30, 'microwave')
    expect(recipes.length).toBeGreaterThan(0)
    expect(recipes.every((r) => r.microwaveOnly)).toBe(true)
  })
  it('never counts expired items as available', () => {
    const [top] = getFallbackSuggestions([item('鶏もも肉', -1, { unit: 'g', quantity: 200 })], [], 500, 20)
    expect(top.matchedIngredients).not.toContain('鶏肉')
  })
})

describe('saved recipes', () => {
  const saved = (id: string, name: string, ingredients: string[]): SavedRecipe => ({
    id, savedAt: '', recipe: { id: 'x', name, description: '', minutes: 10, difficulty: 'かんたん', emoji: '🍳', ingredients, steps: [] },
  })
  const list = [saved('a', '豚キャベツ炒め', ['豚肉', 'キャベツ']), saved('b', '卵かけごはん', ['ごはん', '卵', 'しょうゆ']), saved('c', '親子丼', ['鶏肉', '卵', 'ごはん'])]

  it('re-matches against the current fridge and puts recipes using expiring food first', () => {
    const ranked = rankSavedRecipes(list, [item('卵', 1), item('ご飯', 20), item('鶏もも肉', 0)], ['醤油'])
    expect(ranked.map((r) => r.name)).toEqual(['親子丼', '卵かけごはん', '豚キャベツ炒め'])
    expect(ranked[1].missingIngredients).toEqual([])
    expect(ranked[2].matchPercent).toBe(0)
    expect(ranked[0].id).toBe('saved-c')
  })

  it('keeps saved order when nothing in the fridge helps', () => {
    expect(rankSavedRecipes(list, [], []).map((r) => r.name)).toEqual(['豚キャベツ炒め', '卵かけごはん', '親子丼'])
  })

  it('puts often-cooked dishes first among equals and passes the count through', () => {
    const cooked = list.map((entry) => entry.id === 'a' ? entry : { ...entry, cookedCount: entry.id === 'c' ? 3 : 1 })
    // 豚キャベツ炒め needs 2 purchases; the other two need 3, so it stays first.
    const ranked = rankSavedRecipes(cooked, [], [])
    expect(ranked.map((r) => r.name)).toEqual(['豚キャベツ炒め', '親子丼', '卵かけごはん'])
    expect(ranked.map((r) => r.cookedCount)).toEqual([0, 3, 1])
  })

  it('finds a saved recipe by name and drops pantry-dependent fields when saving', () => {
    expect(findSaved({ name: ' 親子丼 ' }, list)?.id).toBe('c')
    expect(findSaved({ name: '牛丼' }, list)).toBeUndefined()
    const [scored] = rankSavedRecipes(list.slice(0, 1), [], [])
    expect(Object.keys(toSavedPayload(scored))).not.toContain('matchedIngredients')
  })
})
