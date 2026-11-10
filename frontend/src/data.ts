import type { Category, PantryItem, Recipe } from './types'

export const STORAGE_KEY = 'mottainai-kitchen-pantry-v1'
export const CONSUMED_KEY = 'mottainai-kitchen-consumed-v1'
export const AUTH_TOKEN_KEY = 'mottainai-kitchen-auth-token-v1'
export const AUTH_EMAIL_KEY = 'mottainai-kitchen-auth-email-v1'
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
export const categoryOptions: Category[] = ['野菜・果物', '肉・魚', '乳製品・卵', '主食・麺', '調味料', 'その他']
export const categoryEmoji: Record<Category, string> = {
  '野菜・果物': '🥬', '肉・魚': '🥩', '乳製品・卵': '🥚', '主食・麺': '🍚', '調味料': '🧂', 'その他': '🛒',
}

export const demoItems: PantryItem[] = [
  { id: 'demo-1', name: '牛乳', quantity: 1, unit: '本', expiryDate: dateOffset(1), category: '乳製品・卵', emoji: '🥛', note: '開封済み', createdAt: new Date().toISOString() },
  { id: 'demo-2', name: '卵', quantity: 6, unit: '個', expiryDate: dateOffset(3), category: '乳製品・卵', emoji: '🥚', note: '', createdAt: new Date().toISOString() },
  { id: 'demo-3', name: 'ほうれん草', quantity: 1, unit: '袋', expiryDate: dateOffset(0), category: '野菜・果物', emoji: '🥬', note: '', createdAt: new Date().toISOString() },
  { id: 'demo-4', name: '鶏もも肉', quantity: 250, unit: 'g', expiryDate: dateOffset(2), category: '肉・魚', emoji: '🍗', note: '冷蔵', createdAt: new Date().toISOString() },
  { id: 'demo-5', name: 'にんじん', quantity: 2, unit: '本', expiryDate: dateOffset(7), category: '野菜・果物', emoji: '🥕', note: '', createdAt: new Date().toISOString() },
  { id: 'demo-6', name: '食パン', quantity: 4, unit: '枚', expiryDate: dateOffset(-1), category: '主食・麺', emoji: '🍞', note: '', createdAt: new Date().toISOString() },
  { id: 'demo-7', name: 'ミニトマト', quantity: 1, unit: 'パック', expiryDate: dateOffset(5), category: '野菜・果物', emoji: '🍅', note: '', createdAt: new Date().toISOString() },
  { id: 'demo-8', name: '豆腐', quantity: 1, unit: '丁', expiryDate: dateOffset(1), category: 'その他', emoji: '⬜', note: '', createdAt: new Date().toISOString() },
]

export function dateOffset(days: number) {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
export const fallbackRecipes: Omit<Recipe, 'matchedIngredients' | 'missingIngredients' | 'usesExpiring' | 'matchPercent'>[] = [
  { id: 'egg-fried-rice', name: '卵だけでも満足チャーハン', description: 'ごはんと卵があれば作れる、洗い物少なめの定番ごはん。', minutes: 8, difficulty: 'かんたん', emoji: '🍳', ingredients: ['ごはん', '卵', 'しょうゆ'], ingredientDetails: ['ごはん 茶碗1杯', '卵 1個', 'しょうゆ 小さじ1'], estimatedCostYen: 100, servings: 1, steps: ['卵を溶き、フライパンに油をひいて卵に火が通るまで炒める。', 'ごはんを加えてほぐしながら炒める。', 'しょうゆを鍋肌から回し入れて全体を混ぜる。'] },
  { id: 'tofu-don', name: '豆腐のそぼろ風どんぶり', description: 'ひき肉なしでもボリュームが出る、節約向けの一皿。', minutes: 12, difficulty: 'かんたん', emoji: '🍚', ingredients: ['ごはん', '豆腐', 'しょうゆ', '砂糖'], ingredientDetails: ['ごはん 茶碗1杯', '豆腐 1/2丁', 'しょうゆ 大さじ1', '砂糖 小さじ1'], estimatedCostYen: 150, servings: 1, steps: ['豆腐はキッチンペーパーで軽く水気を取る。', 'フライパンで豆腐を崩しながら炒め、水分を飛ばす。', 'しょうゆと砂糖を加えてなじませ、ごはんにのせる。'] },
  { id: 'cabbage-egg', name: 'キャベツと卵のふんわり炒め', description: '余り野菜を使い切りやすい、フライパンひとつの簡単おかず。', minutes: 10, difficulty: 'かんたん', emoji: '🥬', ingredients: ['キャベツ', '卵', '塩こしょう'], ingredientDetails: ['キャベツ 2枚', '卵 1個', '塩こしょう 少々'], estimatedCostYen: 120, servings: 1, steps: ['キャベツを食べやすい大きさにちぎる。', 'フライパンでキャベツを炒め、しんなりしたら溶き卵を加える。', '卵にしっかり火が通るまで混ぜ、塩こしょうで味を調える。'] },
  { id: 'butter-soy-pasta', name: 'きのこのバターしょうゆパスタ', description: 'パスタときのこで作る、材料少なめの一人ごはん。', minutes: 15, difficulty: 'かんたん', emoji: '🍝', ingredients: ['パスタ', 'しめじ', 'しょうゆ', 'バター'], ingredientDetails: ['パスタ 80g', 'しめじ 1/3パック', 'しょうゆ 小さじ2', 'バター 5g'], estimatedCostYen: 220, servings: 1, steps: ['パスタを袋の表示どおりにゆでる。', 'フライパンでしめじを炒め、ゆでたパスタを加える。', 'しょうゆとバターを加えて全体を混ぜる。'] },
  { id: 'tuna-mayo-rice', name: 'ツナマヨたまご丼', description: '火を使う工程を少なくしたい日に。ツナ缶を活用。', minutes: 7, difficulty: 'かんたん', emoji: '🥫', ingredients: ['ごはん', 'ツナ缶', '卵', 'マヨネーズ'], ingredientDetails: ['ごはん 茶碗1杯', 'ツナ缶 1/2缶', '卵 1個', 'マヨネーズ 小さじ1'], estimatedCostYen: 230, servings: 1, steps: ['ツナ缶の油を軽く切り、マヨネーズと混ぜる。', '卵は黄身と白身にしっかり火が通るまで加熱する。', 'ごはんにツナマヨと卵をのせる。'] },
]
