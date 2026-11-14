import type { PantryItem } from '../types'
import { daysUntil, expiryText } from './dates'

export function formatQuantity(value: number) {
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100)
}
/** "卵 残り6個・あと3日" (with ❄️ for frozen food), for stock hints. */
export function stockText(item: PantryItem) {
  return `${item.frozen ? '❄️' : ''}${item.name} 残り${formatQuantity(item.quantity)}${item.unit}・${expiryText(daysUntil(item.expiryDate))}`
}
