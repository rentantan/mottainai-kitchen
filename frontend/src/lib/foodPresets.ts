import type { Category } from '../types'
import { normalize } from './ingredients'

/** Typical values for common groceries, used to pre-fill the add form. `days` is a rough shelf life after purchase. */
export type FoodPreset = { category: Category; emoji: string; unit: string; days: number }

// Order matters: the first entry whose keyword appears in the name wins
// (e.g. 玉ねぎ before ねぎ, ミニトマト before トマト, 卵 before 鶏).
const PRESETS: [string[], FoodPreset][] = [
  [['卵', 'たまご', '玉子'], { category: '乳製品・卵', emoji: '🥚', unit: '個', days: 14 }],
  [['牛乳', 'ミルク', '豆乳'], { category: '乳製品・卵', emoji: '🥛', unit: '本', days: 7 }],
  [['ヨーグルト'], { category: '乳製品・卵', emoji: '🥛', unit: '個', days: 10 }],
  [['チーズ'], { category: '乳製品・卵', emoji: '🧀', unit: '個', days: 14 }],
  [['バター'], { category: '乳製品・卵', emoji: '🧈', unit: '個', days: 30 }],
  [['ひき肉', '挽き肉', '挽肉'], { category: '肉・魚', emoji: '🥩', unit: 'g', days: 1 }],
  [['鶏', 'とり肉', 'ささみ'], { category: '肉・魚', emoji: '🍗', unit: 'g', days: 2 }],
  [['ハム', 'ベーコン', 'ソーセージ', 'ウインナー'], { category: '肉・魚', emoji: '🥓', unit: 'パック', days: 5 }],
  [['豚', '牛肉', '肉'], { category: '肉・魚', emoji: '🥩', unit: 'g', days: 3 }],
  [['鮭', 'さけ', 'サーモン', 'さば', 'ぶり', 'たら', '魚', '刺身'], { category: '肉・魚', emoji: '🐟', unit: '切れ', days: 2 }],
  [['玉ねぎ', 'たまねぎ', '玉葱'], { category: '野菜・果物', emoji: '🧅', unit: '個', days: 30 }],
  [['ねぎ', '葱'], { category: '野菜・果物', emoji: '🌿', unit: '本', days: 7 }],
  [['もやし'], { category: '野菜・果物', emoji: '🌱', unit: '袋', days: 2 }],
  [['ほうれん草', '小松菜', 'ニラ', '水菜', 'チンゲン菜'], { category: '野菜・果物', emoji: '🥬', unit: '袋', days: 3 }],
  [['キャベツ', 'レタス', '白菜'], { category: '野菜・果物', emoji: '🥬', unit: '個', days: 7 }],
  [['にんじん', '人参'], { category: '野菜・果物', emoji: '🥕', unit: '本', days: 10 }],
  [['じゃがいも', 'じゃが芋'], { category: '野菜・果物', emoji: '🥔', unit: '個', days: 30 }],
  [['ミニトマト'], { category: '野菜・果物', emoji: '🍅', unit: 'パック', days: 5 }],
  [['トマト'], { category: '野菜・果物', emoji: '🍅', unit: '個', days: 5 }],
  [['きゅうり'], { category: '野菜・果物', emoji: '🥒', unit: '本', days: 5 }],
  [['なす'], { category: '野菜・果物', emoji: '🍆', unit: '本', days: 5 }],
  [['ピーマン'], { category: '野菜・果物', emoji: '🫑', unit: '個', days: 7 }],
  [['ブロッコリー'], { category: '野菜・果物', emoji: '🥦', unit: '個', days: 4 }],
  [['しめじ', 'えのき', 'まいたけ', 'しいたけ', 'エリンギ', 'きのこ'], { category: '野菜・果物', emoji: '🍄', unit: 'パック', days: 5 }],
  [['バナナ'], { category: '野菜・果物', emoji: '🍌', unit: '本', days: 4 }],
  [['りんご'], { category: '野菜・果物', emoji: '🍎', unit: '個', days: 14 }],
  [['豆腐'], { category: 'その他', emoji: '⬜', unit: '丁', days: 4 }],
  [['納豆'], { category: 'その他', emoji: '🫘', unit: 'パック', days: 7 }],
  [['ツナ', 'サバ缶', '缶詰'], { category: 'その他', emoji: '🥫', unit: '缶', days: 365 }],
  [['キムチ'], { category: 'その他', emoji: '🌶️', unit: 'パック', days: 14 }],
  [['食パン', 'パン'], { category: '主食・麺', emoji: '🍞', unit: '枚', days: 4 }],
  [['冷凍うどん'], { category: '主食・麺', emoji: '🍜', unit: '玉', days: 60 }],
  [['うどん', 'そば', 'ラーメン', '中華麺', '焼きそば'], { category: '主食・麺', emoji: '🍜', unit: '玉', days: 3 }],
  [['パスタ', 'スパゲッティ', 'スパゲティ'], { category: '主食・麺', emoji: '🍝', unit: 'g', days: 365 }],
  [['米', 'ごはん', 'ご飯'], { category: '主食・麺', emoji: '🍚', unit: 'kg', days: 60 }],
  [['しょうゆ', '醤油', '味噌', 'みそ', 'マヨネーズ', 'ケチャップ', 'ソース', 'めんつゆ', 'ポン酢', 'ドレッシング'], { category: '調味料', emoji: '🧂', unit: '本', days: 60 }],
]

const NORMALIZED = PRESETS.map(([keys, preset]) => [keys.map(normalize), preset] as const)

export function findFoodPreset(name: string): FoodPreset | null {
  const n = normalize(name)
  if (!n) return null
  return NORMALIZED.find(([keys]) => keys.some((key) => n.includes(key)))?.[1] ?? null
}
