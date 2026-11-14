import type { Equipment, PantryItem, Recipe, RecipeBase, SavedRecipe } from '../types'
import { daysUntil } from './dates'
import { ingredientMatches, isStaple } from './ingredients'
import { fallbackRecipes } from './sampleData'

export function expiryPriorityPoints(days: number) {
  if (days < 0 || days > 7) return 0
  return [100, 80, 60, 40, 20, 15, 10, 5][days]
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

export function scoreRecipe(recipe: RecipeBase, pantry: PantryItem[], staples: string[]): Recipe {
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
export function getFallbackSuggestions(pantry: PantryItem[], staples: string[], budgetYen = 500, maxMinutes = 20, equipment: Equipment = 'any'): Recipe[] {
  return fallbackRecipes.filter((recipe) => (recipe.estimatedCostYen ?? 9999) <= budgetYen && recipe.minutes <= maxMinutes && (equipment === 'any' || recipe.microwaveOnly)).map((recipe) => scoreRecipe(recipe, pantry, staples)).sort((a, b) => (a.nearestExpiryDays ?? 999) - (b.nearestExpiryDays ?? 999) || (b.expiryPriorityScore ?? 0) - (a.expiryPriorityScore ?? 0) || b.usesExpiring - a.usesExpiring || b.matchPercent - a.matchPercent || (a.estimatedCostYen ?? 9999) - (b.estimatedCostYen ?? 9999)).slice(0, 3)
}

/** The fields of a recipe worth saving; the pantry-dependent ones are recomputed when shown. */
export function toSavedPayload(recipe: Recipe | RecipeBase) {
  const { name, description, minutes, difficulty, emoji, ingredients, ingredientDetails, steps, estimatedCostYen, microwaveOnly, source } = recipe
  return { name, description, minutes, difficulty, emoji, ingredients, ingredientDetails: ingredientDetails ?? [], steps, estimatedCostYen: estimatedCostYen ?? null, microwaveOnly: microwaveOnly ?? false, source: source ?? '' }
}

/** Same dish? Saved recipes are keyed by name (the backend replaces a re-saved name). */
export function findSaved(recipe: { name: string }, saved: SavedRecipe[]) {
  const name = recipe.name.trim()
  return saved.find((entry) => entry.recipe.name === name)
}

/**
 * Saved recipes matched against the current fridge: ones that use soon-to-expire food first,
 * then the ones needing the fewest extra purchases, then the most cooked, then the most recently saved.
 */
export function rankSavedRecipes(saved: SavedRecipe[], pantry: PantryItem[], staples: string[]): Recipe[] {
  return saved
    .filter((entry) => entry.recipe.ingredients?.length)
    .map((entry, index) => ({ index, recipe: { ...scoreRecipe({ ...entry.recipe, id: `saved-${entry.id}` }, pantry, staples), cookedCount: entry.cookedCount ?? 0, lastCookedAt: entry.lastCookedAt ?? null } }))
    .sort((a, b) => (b.recipe.expiryPriorityScore ?? 0) - (a.recipe.expiryPriorityScore ?? 0)
      || a.recipe.missingIngredients.length - b.recipe.missingIngredients.length
      || (b.recipe.cookedCount ?? 0) - (a.recipe.cookedCount ?? 0) || a.index - b.index)
    .map(({ recipe }) => recipe)
}
