import type { PantryItem, Recipe } from './types'
import { STORAGE_KEY, fallbackRecipes } from './data'

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

/** Last pantry snapshot from the server, used only for read-only display while offline. */
export function loadCachedPantry(email: string): PantryItem[] | null {
  try {
    const raw = localStorage.getItem(`${STORAGE_KEY}:${email}`)
    const parsed = raw ? JSON.parse(raw) : null
    return Array.isArray(parsed) ? parsed as PantryItem[] : null
  } catch { return null }
}
export function saveCachedPantry(email: string, items: PantryItem[]) {
  try { localStorage.setItem(`${STORAGE_KEY}:${email}`, JSON.stringify(items)) } catch { /* storage full or disabled */ }
}

export function formatQuantity(value: number) {
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100)
}

export function normalize(s: string) { return s.replace(/[ 　]/g, '').toLowerCase() }
export function expiryPriorityPoints(days: number) {
  if (days < 0 || days > 7) return 0
  return [100, 80, 60, 40, 20, 15, 10, 5][days]
}
export function nameMatches(ingredient: string, name: string) {
  const a = normalize(ingredient)
  const b = normalize(name)
  return Boolean(a && b) && (a.includes(b) || b.includes(a))
}
export function ingredientMatches(ingredient: string, item: PantryItem) {
  return nameMatches(ingredient, item.name)
}
export function isStaple(ingredient: string, staples: string[]) {
  return staples.some((staple) => nameMatches(ingredient, staple))
}
/** Non-expired pantry items matching an ingredient, nearest expiry first. */
export function pantryMatchesFor(ingredient: string, pantry: PantryItem[]) {
  return pantry
    .filter((item) => daysUntil(item.expiryDate) >= 0 && ingredientMatches(ingredient, item))
    .sort((a, b) => a.expiryDate.localeCompare(b.expiryDate))
}

/**
 * Guess how much of a pantry item a recipe line uses, e.g. "鶏もも肉 100g" + unit "g" → 100,
 * "豆腐 1/2丁" + unit "丁" → 0.5. Returns null when the units don't line up.
 */
export function guessAmount(detail: string, unit: string): number | null {
  const pattern = /(\d+(?:\.\d+)?)(?:\s*\/\s*(\d+))?\s*([^\d\s/]+)/g
  for (const match of detail.matchAll(pattern)) {
    const value = match[2] ? Number(match[1]) / Number(match[2]) : Number(match[1])
    if (unit && match[3].startsWith(unit) && Number.isFinite(value) && value > 0) return value
  }
  return null
}

export function scoreRecipe(recipe: typeof fallbackRecipes[number], pantry: PantryItem[], staples: string[]): Recipe {
  const usablePantry = pantry.filter((item) => daysUntil(item.expiryDate) >= 0)
  const matched = recipe.ingredients.filter((ingredient) => usablePantry.some((item) => ingredientMatches(ingredient, item)) || isStaple(ingredient, staples))
  const matchedItems = usablePantry.filter((item) => matched.some((ingredient) => ingredientMatches(ingredient, item)))
  const expiringMatches = matchedItems.filter((item) => daysUntil(item.expiryDate) <= 3)
  const expiryDays = matchedItems.map((item) => daysUntil(item.expiryDate))
  const nearestExpiryDays = expiryDays.length ? Math.min(...expiryDays) : 999
  const priorityScore = expiryDays.reduce((sum, days) => sum + expiryPriorityPoints(days), 0)
  const missing = recipe.ingredients.filter((ingredient) => !matched.includes(ingredient))
  const pct = Math.round((matched.length / recipe.ingredients.length) * 100)
  return { ...recipe, matchedIngredients: matched, missingIngredients: missing, usesExpiring: expiringMatches.length, nearestExpiryDays, expiryPriorityScore: priorityScore, matchPercent: pct }
}
export function getFallbackSuggestions(pantry: PantryItem[], staples: string[], budgetYen = 500, maxMinutes = 20): Recipe[] {
  return fallbackRecipes.filter((recipe) => (recipe.estimatedCostYen ?? 9999) <= budgetYen && recipe.minutes <= maxMinutes).map((recipe) => scoreRecipe(recipe, pantry, staples)).sort((a, b) => (a.nearestExpiryDays ?? 999) - (b.nearestExpiryDays ?? 999) || (b.expiryPriorityScore ?? 0) - (a.expiryPriorityScore ?? 0) || b.usesExpiring - a.usesExpiring || b.matchPercent - a.matchPercent || (a.estimatedCostYen ?? 9999) - (b.estimatedCostYen ?? 9999)).slice(0, 3)
}
