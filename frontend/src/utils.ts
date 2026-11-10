import type { PantryItem, Recipe } from './types'
import { CONSUMED_KEY, STORAGE_KEY, demoItems, fallbackRecipes } from './data'

export function daysUntil(dateString: string) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const target = new Date(`${dateString}T00:00:00`)
  return Math.round((target.getTime() - today.getTime()) / 86400000)
}
export function expiryText(days: number) {
  if (days < 0) return `${Math.abs(days)}日超過`
  if (days === 0) return '今日まで'
  if (days === 1) return '明日まで'
  return `あと${days}日`
}
export function expiryClass(days: number) {
  if (days < 0) return 'expired'
  if (days <= 1) return 'urgent'
  if (days <= 3) return 'soon'
  return 'fresh'
}
export function loadPantry(storageKey = STORAGE_KEY): PantryItem[] {
  try {
    const raw = localStorage.getItem(storageKey)
    return raw ? JSON.parse(raw) as PantryItem[] : demoItems
  } catch { return demoItems }
}
export function loadConsumed(storageKey = CONSUMED_KEY): number {
  try { return Number(localStorage.getItem(storageKey) || '0') } catch { return 0 }
}
export function makeId() { return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}` }


export function normalize(s: string) { return s.replace(/[ 　]/g, '').toLowerCase() }
export function expiryPriorityPoints(days: number) {
  if (days < 0 || days > 7) return 0
  return [100, 80, 60, 40, 20, 15, 10, 5][days]
}
export function ingredientMatches(ingredient: string, item: PantryItem) {
  return normalize(item.name).includes(normalize(ingredient)) || normalize(ingredient).includes(normalize(item.name))
}
export function scoreRecipe(recipe: typeof fallbackRecipes[number], pantry: PantryItem[]): Recipe {
  const usablePantry = pantry.filter((item) => daysUntil(item.expiryDate) >= 0)
  const matched = recipe.ingredients.filter((ingredient) => usablePantry.some((item) => ingredientMatches(ingredient, item)))
  const matchedItems = usablePantry.filter((item) => matched.some((ingredient) => ingredientMatches(ingredient, item)))
  const expiringMatches = matchedItems.filter((item) => daysUntil(item.expiryDate) <= 3)
  const expiryDays = matchedItems.map((item) => daysUntil(item.expiryDate))
  const nearestExpiryDays = expiryDays.length ? Math.min(...expiryDays) : 999
  const priorityScore = expiryDays.reduce((sum, days) => sum + expiryPriorityPoints(days), 0)
  const missing = recipe.ingredients.filter((ingredient) => !matched.includes(ingredient))
  const pct = Math.round((matched.length / recipe.ingredients.length) * 100)
  return { ...recipe, matchedIngredients: matched, missingIngredients: missing, usesExpiring: expiringMatches.length, nearestExpiryDays, expiryPriorityScore: priorityScore, matchPercent: pct }
}
export function getFallbackSuggestions(pantry: PantryItem[], budgetYen = 500, maxMinutes = 20): Recipe[] {
  return fallbackRecipes.filter((recipe) => (recipe.estimatedCostYen ?? 9999) <= budgetYen && recipe.minutes <= maxMinutes).map((recipe) => scoreRecipe(recipe, pantry)).sort((a, b) => (a.nearestExpiryDays ?? 999) - (b.nearestExpiryDays ?? 999) || (b.expiryPriorityScore ?? 0) - (a.expiryPriorityScore ?? 0) || b.usesExpiring - a.usesExpiring || b.matchPercent - a.matchPercent || (a.estimatedCostYen ?? 9999) - (b.estimatedCostYen ?? 9999)).slice(0, 3)
}
