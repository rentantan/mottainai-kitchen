/** Ingredient-name matching. Same rules as backend/ingredients.py. */
import type { PantryItem } from '../types'
import { daysUntil } from './dates'

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
/**
 * Recently used-up foods worth buying again: not in the fridge (unexpired) and not already on the open shopping list.
 */
export function restockCandidates(names: string[], pantry: PantryItem[], openShopping: string[]) {
  return names.filter((name) => pantryMatchesFor(name, pantry).length === 0 && !openShopping.some((other) => nameMatches(name, other)))
}
