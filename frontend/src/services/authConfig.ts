export interface AuthConfig { url: string; publishableKey: string; appUrl: string }

/** VITE values are public. Accept only the publishable key family, never elevated keys. */
export function readAuthConfig(env: Record<string, unknown>): AuthConfig | null {
  const url = typeof env.VITE_SUPABASE_URL === 'string' ? env.VITE_SUPABASE_URL.trim() : ''
  const publishableKey = typeof env.VITE_SUPABASE_PUBLISHABLE_KEY === 'string' ? env.VITE_SUPABASE_PUBLISHABLE_KEY.trim() : ''
  const appUrl = typeof env.VITE_APP_URL === 'string' ? env.VITE_APP_URL.trim() : ''
  try {
    const project = new URL(url)
    const app = new URL(appUrl)
    const safeOrigin = (value: URL) => (value.protocol === 'https:' || (value.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(value.hostname)))
      && !value.username && !value.password && !value.search && !value.hash && value.pathname === '/'
    if (!safeOrigin(project) || !safeOrigin(app) || !/^sb_publishable_[A-Za-z0-9_-]+$/.test(publishableKey)) return null
    return { url: project.origin, publishableKey, appUrl: app.origin }
  } catch { return null }
}
