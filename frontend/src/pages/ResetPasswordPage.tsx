import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import PasswordInput from '../components/auth/PasswordInput'
import PasswordRecoveryLayout, { RecoveryError, RecoverySubmitButton } from '../components/auth/PasswordRecoveryLayout'
import { PasswordRecoveryError, updatePassword } from '../services/passwordRecovery'

function validatePassword(password: string) {
  return password.length >= 8 && /[A-Za-z]/.test(password) && /[0-9]/.test(password)
    ? '' : 'Use 8+ characters, with a letter and a number.'
}

export default function ResetPasswordPage() {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [visible, setVisible] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  const passwordInput = useRef<HTMLInputElement>(null)
  const confirmInput = useRef<HTMLInputElement>(null)
  const passwordError = submitted ? validatePassword(password) : ''
  const confirmError = !submitted ? '' : !confirm ? 'Re-enter your new password.' : password !== confirm ? "Passwords don't match." : ''

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending.current) return
    setSubmitted(true)
    setError('')
    if (validatePassword(password)) { passwordInput.current?.focus(); return }
    if (!confirm || password !== confirm) { confirmInput.current?.focus(); return }
    pending.current = true
    setLoading(true)
    try {
      await updatePassword(password)
      // Success UI and redirects require a verified recovery session and a real update.
    } catch (cause) {
      setError(cause instanceof PasswordRecoveryError && cause.code === 'not_configured'
        ? 'Password reset is not connected yet. Your password has not been changed. A verified recovery link will be required when Supabase Auth is integrated.'
        : 'Unable to update your password right now. Please request a new recovery link and try again later.')
    } finally {
      pending.current = false
      setLoading(false)
    }
  }

  return (
    <PasswordRecoveryLayout title="Choose a new password" description="8+ characters, with a letter and a number.">
      {error && <RecoveryError message={error} />}
      <form onSubmit={handleSubmit} noValidate className="login-form" aria-busy={loading}>
        <div className="login-field">
          <label htmlFor="fp-new">New password</label>
          <PasswordInput id="fp-new" inputRef={passwordInput} value={password} onChange={(value) => { setPassword(value); setError('') }} disabled={loading} invalid={Boolean(passwordError)} describedBy={passwordError ? 'fp-new-error' : undefined} autoComplete="new-password" visible={visible} onVisibilityChange={setVisible} controls="fp-new fp-confirm" />
          {passwordError && <span id="fp-new-error" className="login-field-error">{passwordError}</span>}
        </div>
        <div className="login-field">
          <label htmlFor="fp-confirm">Confirm new password</label>
          <input ref={confirmInput} id="fp-confirm" name="confirm_password" type={visible ? 'text' : 'password'} autoComplete="new-password" required value={confirm} onChange={(event) => { setConfirm(event.target.value); setError('') }} disabled={loading} aria-invalid={Boolean(confirmError)} aria-describedby={confirmError ? 'fp-confirm-error' : undefined} />
          {confirmError && <span id="fp-confirm-error" className="login-field-error">{confirmError}</span>}
        </div>
        <RecoverySubmitButton loading={loading} label="Save new password" loadingLabel="Saving password…" />
      </form>
    </PasswordRecoveryLayout>
  )
}
