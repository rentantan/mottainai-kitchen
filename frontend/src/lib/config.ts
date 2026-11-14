/** Build-time settings and localStorage keys. Keys are suffixed with `:<email>` where per-account. */
export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
export const STORAGE_KEY = 'mottainai-kitchen-pantry-v1'
export const AUTH_TOKEN_KEY = 'mottainai-kitchen-auth-token-v1'
export const AUTH_EMAIL_KEY = 'mottainai-kitchen-auth-email-v1'
export const PREFS_KEY = 'mottainai-kitchen-recipe-prefs-v1'
