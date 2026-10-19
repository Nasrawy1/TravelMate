import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import RivieraLogo from '../components/welcome/RivieraLogo'
import PasswordInput from '../components/auth/PasswordInput'
import AuthSessionNotice from '../components/auth/AuthSessionNotice'
import { useAuthSession } from '../components/auth/AuthSessionProvider'
import { signIn, SignInError } from '../services/auth'
import '../styles/welcome.css'
import '../styles/login.css'

function validateEmail(email: string) {
  if (!email.trim()) return 'Enter your email address.'
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) ? '' : 'Enter a valid email, like name@example.com.'
}

const errorMessages = {
  not_configured: { title: 'Sign-in is not configured', message: 'Local Supabase configuration is missing or invalid. You have not been signed in.' },
  invalid_credentials: { title: 'Wrong email or password', message: 'Check both and try again. Passwords are case-sensitive.' },
  email_not_confirmed: { title: 'Confirm your email first', message: 'Complete email confirmation, then return here to sign in.' },
  weak_password: { title: 'Unable to sign in', message: 'Check your password and try again.' },
  rate_limited: { title: 'Please wait before trying again', message: 'Too many authentication requests. Try again later.' },
  unavailable: { title: 'Unable to sign in', message: 'Sign-in is unavailable right now. Please try again later.' },
}

export default function LoginPage() {
  const auth = useAuthSession()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<keyof typeof errorMessages | null>(null)
  const pending = useRef(false)
  const emailInput = useRef<HTMLInputElement>(null)
  const passwordInput = useRef<HTMLInputElement>(null)
  const emailError = submitted ? validateEmail(email) : ''
  const passwordError = submitted && !password ? 'Enter your password.' : ''
  const wrongCredentials = error === 'invalid_credentials'

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending.current) return
    setSubmitted(true)
    setError(null)
    if (validateEmail(email)) { emailInput.current?.focus(); return }
    if (!password) { passwordInput.current?.focus(); return }

    pending.current = true
    setLoading(true)
    try {
      await signIn({ email: email.trim(), password })
      setPassword('')
      await auth.refresh()
    } catch (cause) {
      setError(cause instanceof SignInError ? cause.code : 'unavailable')
    } finally {
      pending.current = false
      setLoading(false)
    }
  }

  return (
    <div className="welcome login-page">
      <a className="skip-link" href="#login-content">Skip to sign-in form</a>
      <aside className="login-panel" aria-labelledby="login-welcome">
        <svg className="login-seascape" viewBox="0 0 620 620" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
          <rect width="620" height="620" fill="#EFD9C2" />
          <circle cx="310" cy="290" r="130" fill="#E9A15A" />
          <path d="M0 380c80-30 160-30 240 0s160 30 240 0 100-25 140-12v272H0z" fill="#2C5C8A" />
          <path d="M0 440c80-25 160-25 240 0s160 25 240 0 100-18 140-8" stroke="#EFD9C2" strokeWidth="5" fill="none" />
          <path d="M0 500c80-25 160-25 240 0s160 25 240 0 100-18 140-8" stroke="#EFD9C2" strokeWidth="4" fill="none" opacity="0.6" />
        </svg>
        <RivieraLogo />
        <div className="login-panel-copy">
          <h1 id="login-welcome">Welcome <em>back.</em></h1>
          <p>Your next trip is a few clicks away.</p>
        </div>
        <div className="login-postcard"><span>POSTCARD</span><p>Plan the whole trip around one budget.</p></div>
      </aside>

      <main id="login-content" className="login-main" tabIndex={-1}>
        <div className="login-back-row"><Link to="/" className="login-back-link"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M19 12H5M11 6l-6 6 6 6" /></svg>Back to home</Link></div>
        <div className="login-card-position">
          <section className="login-card" aria-labelledby="login-title">
            {auth.status !== 'authenticated' && <div className="login-card-heading"><h2 id="login-title">{auth.status === 'checking' ? 'Checking your session' : 'Sign in'}</h2>{auth.status !== 'checking' && <p>New here? <Link to="/signup">Create an account</Link></p>}</div>}
            <AuthSessionNotice headingId="login-title" />
            {error && auth.status !== 'authenticated' && <div className="login-error-banner" role="alert">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5M12 16.5v.5" /></svg>
              <div><strong>{errorMessages[error].title}</strong><p>{errorMessages[error].message}</p></div>
            </div>}
            {auth.status !== 'authenticated' && auth.status !== 'checking' && <form onSubmit={handleSubmit} noValidate className="login-form" aria-busy={loading}>
              <div className="login-field">
                <label htmlFor="login-email">Email</label>
                <input ref={emailInput} id="login-email" name="email" type="email" autoComplete="email" placeholder="name@example.com" required disabled={loading} value={email} onChange={(event) => { setEmail(event.target.value); setError(null) }} aria-invalid={Boolean(emailError) || wrongCredentials} aria-describedby={emailError ? 'login-email-error' : undefined} />
                {emailError && <span id="login-email-error" className="login-field-error">{emailError}</span>}
              </div>
              <div className="login-field">
                <div className="login-password-label"><label htmlFor="login-password">Password</label><Link to="/forgot-password">Forgot password?</Link></div>
                <PasswordInput inputRef={passwordInput} id="login-password" value={password} onChange={(value) => { setPassword(value); setError(null) }} disabled={loading} invalid={Boolean(passwordError) || wrongCredentials} describedBy={passwordError ? 'login-password-error' : undefined} />
                {passwordError && <span id="login-password-error" className="login-field-error">{passwordError}</span>}
              </div>
              <button type="submit" className="login-submit" disabled={loading}>
                {loading && <svg className="login-spinner" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9" /></svg>}
                <span aria-live="polite">{loading ? 'Signing in…' : 'Sign in'}</span>
              </button>
            </form>}
            <div className="login-divider"><span />or<span /></div>
            <Link to="/offline-demo" className="login-demo-link"><span>DEMO</span>Demo trips are coming soon.</Link>
          </section>
        </div>
      </main>
    </div>
  )
}
