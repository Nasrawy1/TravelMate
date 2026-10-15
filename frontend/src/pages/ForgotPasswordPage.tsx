import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import PasswordRecoveryLayout, { RecoveryError, RecoverySubmitButton } from '../components/auth/PasswordRecoveryLayout'
import { PasswordRecoveryError, requestPasswordReset } from '../services/passwordRecovery'

function validateEmail(email: string) {
  if (!email.trim()) return 'Enter your email address.'
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()) ? '' : 'Enter a valid email, like name@example.com.'
}

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const emailInput = useRef<HTMLInputElement>(null)
  const pending = useRef(false)
  const emailError = submitted ? validateEmail(email) : ''

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending.current) return
    setSubmitted(true)
    setError('')
    if (validateEmail(email)) { emailInput.current?.focus(); return }
    pending.current = true
    setLoading(true)
    try {
      await requestPasswordReset(email.trim())
      // Only a real accepted provider request may lead to an email notice.
    } catch (cause) {
      setError(cause instanceof PasswordRecoveryError && cause.code === 'not_configured'
        ? 'Password recovery is not connected yet. No reset email has been sent.'
        : 'Unable to request a reset link right now. Please try again later.')
    } finally {
      pending.current = false
      setLoading(false)
    }
  }

  return (
    <PasswordRecoveryLayout title="Reset your password" description="Enter the email you signed up with to request a link to choose a new password.">
      {error && <RecoveryError message={error} />}
      <form onSubmit={handleSubmit} noValidate className="login-form" aria-busy={loading}>
        <div className="login-field">
          <label htmlFor="fp-email">Email</label>
          <input ref={emailInput} id="fp-email" name="email" type="email" autoComplete="email" placeholder="name@example.com" required value={email} onChange={(event) => { setEmail(event.target.value); setError('') }} disabled={loading} aria-invalid={Boolean(emailError)} aria-describedby={emailError ? 'fp-email-error' : undefined} />
          {emailError && <span id="fp-email-error" className="login-field-error">{emailError}</span>}
        </div>
        <RecoverySubmitButton loading={loading} label="Send reset link" loadingLabel="Sending link…" />
      </form>
    </PasswordRecoveryLayout>
  )
}
