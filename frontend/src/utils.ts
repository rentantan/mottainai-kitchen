import type { PantryItem, Recipe, RecipeBase, SavedRecipe } from './types'
import { STORAGE_KEY, fallbackRecipes } from './data'
import type { Equipment } from './data'

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
/** Forget everything this device kept for an account (after the account is deleted). */
export function clearLocalData(email: string, keys: string[]) {
  for (const key of [STORAGE_KEY, ...keys]) {
    try { localStorage.removeItem(`${key}:${email}`) } catch { /* storage disabled */ }
  }
}
export function saveCachedPantry(email: string, items: PantryItem[]) {
  try { localStorage.setItem(`${STORAGE_KEY}:${email}`, JSON.stringify(items)) } catch { /* storage full or disabled */ }
}

export function formatQuantity(value: number) {
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100)
}

/**
 * Spellings of the same ingredient; the first entry is canonical.
 * Keep in sync with backend/ingredients.py (ALIAS_GROUPS).
 */
const INGREDIENT_ALIAS_GROUPS: string[][] = [
  ['ごはん', 'ご飯', '白米', '米', 'ライス', '白ごはん'],
  ['卵', 'たまご', '玉子', '鶏卵'],
  ['鶏肉', '鶏もも肉', '鶏むね肉', '鶏胸肉', '鶏もも', '鶏むね', 'とり肉', 'ささみ', '鶏ささみ'],
  ['豚肉', '豚こま', '豚こま肉', '豚こま切れ肉', '豚バラ', '豚バラ肉', '豚ロース'],
  ['ひき肉', '挽き肉', '挽肉', '合いびき肉', '合挽き肉'],
  ['ねぎ', '長ねぎ', '青ねぎ', '万能ねぎ', '小ねぎ', '葱', '長葱'],
  ['玉ねぎ', 'たまねぎ', '玉葱'],
  ['にんじん', '人参'],
  ['じゃがいも', 'じゃが芋', '馬鈴薯'],
  ['ほうれん草', 'ほうれんそう'],
  ['しょうゆ', '醤油', 'しょう油'],
  ['塩こしょう', '塩胡椒'],
  ['こしょう', '胡椒'],
  ['砂糖', 'さとう'],
  ['味噌', 'みそ'],
  ['豆腐', 'とうふ', '絹豆腐', '木綿豆腐'],
  ['ツナ缶', 'ツナ', 'シーチキン'],
  ['パスタ', 'スパゲッティ', 'スパゲティ'],
  ['牛乳', 'ミルク'],
  ['しめじ', 'ぶなしめじ'],
  ['コンソメ', '顆粒コンソメ', '固形コンソメ'],
  ['めんつゆ', '麺つゆ'],
  ['ポン酢', 'ぽんず'],
  // Single-character seasonings get their own groups so the longest-ending rule tells them apart (醤油 ≠ 油, ポン酢 ≠ 酢).
  ['サラダ油', '油', '植物油', 'キャノーラ油', 'サラダオイル'],
  ['ごま油'],
  ['ラー油'],
  ['オリーブオイル', 'オリーブ油'],
  ['酢', '米酢', '穀物酢'],
  ['塩', '食塩', 'あら塩'],
  ['酒', '料理酒', '日本酒'],
  ['みりん', '本みりん'],
]

/** Remove spaces, unify full/half width and katakana→hiragana so ネギ / ねぎ compare equal. */
export function normalize(s: string) {
  return s.normalize('NFKC').replace(/\s/g, '').replace(/[ァ-ヶ]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0x60)).toLowerCase()
}
const CANONICAL = new Map(INGREDIENT_ALIAS_GROUPS.flatMap((group) => group.map((alias) => [normalize(alias), normalize(group[0])] as const)))
// Longest first, so 玉ねぎ wins over ねぎ and 醤油 over 油.
const ALIASES_BY_LENGTH = [...CANONICAL.keys()].sort((a, b) => b.length - a.length)

/** Drop bracketed notes, amounts and leftover words: 卵(Mサイズ) → 卵, キャベツ1/2 → キャベツ, 豆腐半分 → 豆腐. */
function core(s: string) {
  const n = normalize(s)
  const stripped = n.replace(/\(.*?\)|\[.*?\]|【.*?】|「.*?」/g, '').replace(/(?<=.)\d.*$/, '').replace(/(半分|半玉|半丁|半袋|少々|適量|適宜|残り)$/, '')
  return stripped || n
}

/** Canonical food named by the longest known ending (国産鶏もも肉 → 鶏肉, 新玉ねぎ → 玉ねぎ, 卵豆腐 → 豆腐), or null. */
export function headFood(s: string) {
  const c = core(s)
  const alias = ALIASES_BY_LENGTH.find((key) => c.endsWith(key))
  return alias === undefined ? null : CANONICAL.get(alias) ?? null
}

export function expiryPriorityPoints(days: number) {
  if (days < 0 || days > 7) return 0
  return [100, 80, 60, 40, 20, 15, 10, 5][days]
}
/**
 * Same food? Names ending with a known food match only when that food is the same (長ねぎ ≠ 玉ねぎ, 油 ≠ 醤油, 鶏もも肉 ≒ 鶏肉).
 * Otherwise the shorter name (2+ characters) must end the longer one (トマト ≒ ミニトマト), so 米 ≠ 米酢.
 * Keep in sync with backend/ingredients.py (matches_name).
 */
export function nameMatches(ingredient: string, name: string) {
  const a = core(ingredient)
  const b = core(name)
  if (!a || !b) return false
  if (a === b) return true
  const ha = headFood(a)
  const hb = headFood(b)
  if (ha !== null || hb !== null) return ha === hb
  const [shorter, longer] = a.length <= b.length ? [a, b] : [b, a]
  return shorter.length >= 2 && longer.endsWith(shorter)
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
/** Pantry items of the same food, expired ones included (for "you already have this" hints), nearest expiry first. */
export function sameFoodInPantry(name: string, pantry: PantryItem[]) {
  if (!name.trim()) return []
  return pantry.filter((item) => nameMatches(name, item.name)).sort((a, b) => a.expiryDate.localeCompare(b.expiryDate))
}
/** "卵 残り6個・あと3日" (with ❄️ for frozen food), for stock hints. */
export function stockText(item: PantryItem) {
  return `${item.frozen ? '❄️' : ''}${item.name} 残り${formatQuantity(item.quantity)}${item.unit}・${expiryText(daysUntil(item.expiryDate))}`
}
/**
 * Recently used-up foods worth buying again: not in the fridge (unexpired) and not already on the open shopping list.
 */
export function restockCandidates(names: string[], pantry: PantryItem[], openShopping: string[]) {
  return names.filter((name) => pantryMatchesFor(name, pantry).length === 0 && !openShopping.some((other) => nameMatches(name, other)))
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
