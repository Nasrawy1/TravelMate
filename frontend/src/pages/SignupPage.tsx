import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import PasswordInput from '../components/auth/PasswordInput'
import RivieraLogo from '../components/welcome/RivieraLogo'
import AuthSessionNotice from '../components/auth/AuthSessionNotice'
import { useAuthSession } from '../components/auth/AuthSessionProvider'
import { signUp, SignUpError } from '../services/signup'
import '../styles/welcome.css'
import '../styles/login.css'
import '../styles/signup.css'

const benefits = ['Day-by-day AI itinerary', 'Real, clearly labeled prices', 'An honest budget check']
const errorMessages = {
  not_configured: { title: 'Account creation is not configured', message: 'Local Supabase configuration is missing or invalid. No signup request was sent.' },
  invalid_credentials: { title: 'Unable to create an account', message: 'Check your details and try again.' },
  email_not_confirmed: { title: 'Confirm your email', message: 'Complete email confirmation, then sign in.' },
  weak_password: { title: 'Choose a stronger password', message: 'Your password does not meet the configured security requirements.' },
  rate_limited: { title: 'Please wait before trying again', message: 'Too many authentication requests. Try again later.' },
  unavailable: { title: 'Unable to create an account', message: 'Account creation is unavailable right now. Please try again later.' },
}

function CheckIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
}

export default function SignupPage() {
  const auth = useAuthSession()
  const [confirmationRequired, setConfirmationRequired] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<keyof typeof errorMessages | null>(null)
  const pending = useRef(false)
  const nameInput = useRef<HTMLInputElement>(null)
  const emailInput = useRef<HTMLInputElement>(null)
  const passwordInput = useRef<HTMLInputElement>(null)
  const confirmInput = useRef<HTMLInputElement>(null)

  const rules = [
    { label: '8+ characters', met: password.length >= 8 },
    { label: 'A letter', met: /[A-Za-z]/.test(password) },
    { label: 'A number', met: /[0-9]/.test(password) },
  ]
  const passwordValid = rules.every((rule) => rule.met)
  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
  const nameError = submitted && !name.trim() ? 'Enter your name.' : ''
  const emailError = !submitted ? '' : !email.trim() ? 'Enter your email address.' : !emailValid ? 'Enter a valid email, like name@example.com.' : ''
  const confirmError = !submitted ? '' : !confirm ? 'Re-enter your password.' : confirm !== password ? "Passwords don't match." : ''

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending.current) return
    setSubmitted(true)
    setError(null)
    if (!name.trim()) { nameInput.current?.focus(); return }
    if (!emailValid) { emailInput.current?.focus(); return }
    if (!passwordValid) { passwordInput.current?.focus(); return }
    if (!confirm || confirm !== password) { confirmInput.current?.focus(); return }

    pending.current = true
    setLoading(true)
    try {
      const outcome = await signUp({ name: name.trim(), email: email.trim(), password })
      setPassword(''); setConfirm(''); setSubmitted(false)
      setConfirmationRequired(outcome === 'confirmation_required')
      if (outcome === 'session_received') await auth.refresh()
    } catch (cause) {
      setError(cause instanceof SignUpError ? cause.code : 'unavailable')
    } finally {
      pending.current = false
      setLoading(false)
    }
  }

  return (
    <div className="welcome login-page signup-page">
      <a className="skip-link" href="#signup-content">Skip to signup form</a>
      <aside className="login-panel" aria-labelledby="signup-welcome">
        <svg className="login-seascape" viewBox="0 0 620 620" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
          <rect width="620" height="620" fill="#EFD9C2" />
          <circle cx="310" cy="290" r="130" fill="#E9A15A" />
          <path d="M0 380c80-30 160-30 240 0s160 30 240 0 100-25 140-12v272H0z" fill="#2C5C8A" />
          <path d="M0 440c80-25 160-25 240 0s160 25 240 0 100-18 140-8" stroke="#EFD9C2" strokeWidth="5" fill="none" />
          <path d="M0 500c80-25 160-25 240 0s160 25 240 0 100-18 140-8" stroke="#EFD9C2" strokeWidth="4" fill="none" opacity="0.6" />
        </svg>
        <RivieraLogo />
        <div className="login-panel-copy">
          <h1 id="signup-welcome">{auth.status === 'authenticated' ? <>Welcome <em>back.</em></> : <>{auth.status === 'checking' ? 'Your next trip starts ' : 'Your first trip starts '}<em>here.</em></>}</h1>
          <ul className="signup-benefits">{benefits.map((benefit) => <li key={benefit}><CheckIcon />{benefit}</li>)}</ul>
        </div>
        <div className="signup-payment-note">No payment details needed. We never book or charge.</div>
      </aside>
      <main id="signup-content" className="login-main" tabIndex={-1}>
        <div className="login-back-row"><Link to="/" className="login-back-link"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M19 12H5M11 6l-6 6 6 6" /></svg>Back to home</Link></div>
        <div className="login-card-position">
          <section className="login-card" aria-labelledby="signup-title">
            {auth.status !== 'authenticated' && <div className="login-card-heading"><h2 id="signup-title">{auth.status === 'checking' ? 'Checking your session' : 'Create your account'}</h2>{auth.status !== 'checking' && <p>Already have one? <Link to="/login">Sign in</Link></p>}</div>}
            <AuthSessionNotice headingId="signup-title" />
            {confirmationRequired && auth.status !== 'authenticated' && <div className="auth-session-notice" role="status"><strong>Check your email to confirm</strong><p>If signup is eligible, Supabase will send confirmation instructions. Email delivery has not been verified. This signup response did not establish a session. Open the confirmation link to verify your email, or <Link to="/login">return to sign in</Link> after confirming.</p></div>}
            {error && auth.status !== 'authenticated' && <div className="login-error-banner" role="alert">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5M12 16.5v.5" /></svg>
              <div><strong>{errorMessages[error].title}</strong><p>{errorMessages[error].message}</p></div>
            </div>}
            {!confirmationRequired && auth.status !== 'authenticated' && auth.status !== 'checking' && <form onSubmit={handleSubmit} noValidate className="login-form signup-form" aria-busy={loading}>
              <div className="login-field">
                <label htmlFor="su-name">Name</label>
                <input ref={nameInput} id="su-name" name="name" type="text" autoComplete="name" placeholder="What should we call you?" required value={name} onChange={(event) => { setName(event.target.value); setError(null) }} disabled={loading} aria-invalid={Boolean(nameError)} aria-describedby={nameError ? 'su-name-error' : undefined} />
                {nameError && <span id="su-name-error" className="login-field-error">{nameError}</span>}
              </div>
              <div className="login-field">
                <label htmlFor="su-email">Email</label>
                <input ref={emailInput} id="su-email" name="email" type="email" autoComplete="email" placeholder="name@example.com" required value={email} onChange={(event) => { setEmail(event.target.value); setError(null) }} disabled={loading} aria-invalid={Boolean(emailError)} aria-describedby={emailError ? 'su-email-error' : undefined} />
                {emailError && <span id="su-email-error" className="login-field-error">{emailError}</span>}
              </div>
              <div className="login-field">
                <label htmlFor="su-password">Password</label>
                <PasswordInput id="su-password" inputRef={passwordInput} value={password} onChange={(value) => { setPassword(value); setError(null) }} disabled={loading} invalid={submitted && !passwordValid} describedBy="su-password-rules" autoComplete="new-password" visible={showPassword} onVisibilityChange={setShowPassword} controls="su-password su-confirm" />
                <ul id="su-password-rules" className="signup-password-rules" aria-live="polite">
                  {rules.map((rule) => <li key={rule.label} className={rule.met ? 'signup-rule-met' : submitted ? 'signup-rule-error' : ''}>
                    {rule.met && <CheckIcon />}<span>{rule.label}</span><span className="signup-visually-hidden">{rule.met ? ' — met' : ' — not met'}</span>
                  </li>)}
                </ul>
              </div>
              <div className="login-field">
                <label htmlFor="su-confirm">Confirm password</label>
                <input ref={confirmInput} id="su-confirm" name="confirm_password" type={showPassword ? 'text' : 'password'} autoComplete="new-password" required value={confirm} onChange={(event) => { setConfirm(event.target.value); setError(null) }} disabled={loading} aria-invalid={Boolean(confirmError)} aria-describedby={confirmError ? 'su-confirm-error' : undefined} />
                {confirmError && <span id="su-confirm-error" className="login-field-error">{confirmError}</span>}
              </div>
              <button type="submit" className="login-submit signup-submit" disabled={loading}>
                {loading && <svg className="login-spinner" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9" /></svg>}
                <span aria-live="polite">{loading ? 'Creating account…' : 'Create account'}</span>
              </button>
            </form>}
            <Link to="/offline-demo" className="login-demo-link"><span>DEMO</span>Explore a demo trip</Link>
          </section>
        </div>
      </main>
    </div>
  )
}
