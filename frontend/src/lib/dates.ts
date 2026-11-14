/** Local calendar date `days` from today, as YYYY-MM-DD (the format of expiryDate). */
export function dateOffset(days: number) {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
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
