export type Category = '野菜・果物' | '肉・魚' | '乳製品・卵' | '主食・麺' | '調味料' | 'その他'
export type PantryItem = {
  id: string
  name: string
  quantity: number
  unit: string
  expiryDate: string
  category: Category
  emoji: string
  note: string
  createdAt: string
}
export type Recipe = {
  id: string
  name: string
  description: string
  minutes: number
  difficulty: 'かんたん' | 'ふつう'
  emoji: string
  ingredients: string[]
  matchedIngredients: string[]
  missingIngredients: string[]
  steps: string[]
  usesExpiring: number
  matchPercent: number
  sourceUrl?: string
  imageUrl?: string
  source?: string
  ingredientDetails?: string[]
  estimatedCostYen?: number
  servings?: number
  expiryPriorityScore?: number
  nearestExpiryDays?: number
}

export type ShoppingItem = {
  id: string
  name: string
  checked: boolean
  createdAt: string
}
export type WasteEntry = {
  id: string
  name: string
  quantity: number
  unit: string
  category: Category
  emoji: string
  expiryDate: string
  discardedAt: string
}
/** Discarded food ("もったいない記録"): recent entries plus all-time / this-month counts. */
export type WasteSummary = { items: WasteEntry[]; totalCount: number; monthCount: number }
export type PantryState = { items: PantryItem[]; consumedCount: number; initialized: boolean; waste: WasteSummary }
