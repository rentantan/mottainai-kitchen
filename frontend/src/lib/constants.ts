import type { Category } from '../types'

export const categoryOptions: Category[] = ['野菜・果物', '肉・魚', '乳製品・卵', '主食・麺', '調味料', 'その他']
/** Categories that keep well in the freezer, and roughly how long (days) once frozen. */
export const FREEZABLE_CATEGORIES: Category[] = ['肉・魚', '主食・麺', '野菜・果物', 'その他']
export const FREEZER_DAYS = 30
export const categoryEmoji: Record<Category, string> = {
  '野菜・果物': '🥬', '肉・魚': '🥩', '乳製品・卵': '🥚', '主食・麺': '🍚', '調味料': '🧂', 'その他': '🛒',
}
