import { API_BASE } from './data'

// Backend caps one recipe request (incl. Gemini retries) at GEMINI_TOTAL_DEADLINE_SECONDS (45s).
// Keep this longer so the browser never gives up while the backend is still working.
export const FRONTEND_TIMEOUT_MS = 60_000

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

type ValidationDetail = { loc?: (string | number)[]; msg?: string }

const FIELD_LABELS: Record<string, string> = {
  email: 'メールアドレス', password: 'パスワード', name: '食材名', quantity: '残量', unit: '単位',
  expiryDate: '期限', category: 'カテゴリ', note: 'メモ', amount: '使った量', names: '名前',
}

/** Turn FastAPI's `detail` (string or validation-error array) into a Japanese message. */
export function describeDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as ValidationDetail
    const field = [...(first.loc ?? [])].reverse().find((part) => typeof part === 'string' && FIELD_LABELS[part])
    return field ? `${FIELD_LABELS[field as string]}の入力内容を確認してください。` : '入力内容を確認してください。'
  }
  return fallback
}

export async function apiFetch<T>(path: string, options: { token?: string; method?: string; body?: unknown; timeoutMs?: number } = {}): Promise<T> {
  const headers = new Headers()
  if (options.token) headers.set('Authorization', `Bearer ${options.token}`)
  if (options.body !== undefined) headers.set('Content-Type', 'application/json')
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: AbortSignal.timeout(options.timeoutMs ?? 15_000),
    })
  } catch (cause) {
    const timedOut = cause instanceof DOMException && cause.name === 'TimeoutError'
    throw new ApiError(timedOut ? 'サーバーの応答がありません。しばらくしてから再試行してください。' : 'サーバーに接続できません。バックエンドが起動しているか確認してください。', 0)
  }
  let data: unknown = null
  try { data = await response.json() } catch { /* empty or non-JSON body */ }
  if (!response.ok) {
    const detail = data && typeof data === 'object' ? (data as { detail?: unknown }).detail : undefined
    throw new ApiError(describeDetail(detail, `エラーが発生しました（HTTP ${response.status}）`), response.status)
  }
  return data as T
}
