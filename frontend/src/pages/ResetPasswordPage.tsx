import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import PasswordInput from '../components/auth/PasswordInput'
import PasswordRecoveryLayout, { RecoveryError, RecoverySubmitButton } from '../components/auth/PasswordRecoveryLayout'
import { PasswordRecoveryError, updatePassword } from '../services/passwordRecovery'
import { useEmailAuth } from '../components/auth/EmailAuthProvider'
import { Link } from 'react-router-dom'

function validatePassword(password: string) {
  return password.length >= 8 && /[A-Za-z]/.test(password) && /[0-9]/.test(password)
    ? '' : 'Use 8+ characters, with a letter and a number.'
}

export default function ResetPasswordPage() {
  const recovery = useEmailAuth()
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
  useEffect(() => {
    if (recovery.recovery === 'locked' || recovery.recovery === 'complete') { setPassword(''); setConfirm(''); setSubmitted(false) }
  }, [recovery.recovery])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending.current || recovery.recovery !== 'ready') return
    setSubmitted(true)
    setError('')
    if (validatePassword(password)) { passwordInput.current?.focus(); return }
    if (!confirm || password !== confirm) { confirmInput.current?.focus(); return }
    pending.current = true
    setLoading(true)
    try {
      await updatePassword(password)
      setPassword(''); setConfirm('')
    } catch (cause) {
      setError(cause instanceof PasswordRecoveryError && cause.code === 'weak_password'
        ? 'Choose a stronger password that meets the configured security policy.'
        : cause instanceof PasswordRecoveryError && cause.code === 'same_password'
          ? 'Choose a password different from your current password.'
          : cause instanceof PasswordRecoveryError && cause.code === 'rate_limited'
            ? 'Please wait before trying again. Your password update is not retried automatically.'
            : 'Unable to update your password. Request a fresh recovery link if your authorization expired.')
    } finally {
      pending.current = false
      setLoading(false)
    }
  }

  return (
    <PasswordRecoveryLayout
      title={recovery.recovery === 'complete' ? 'Password updated successfully' : 'Choose a new password'}
      description={recovery.recovery === 'complete' ? 'Use your new password the next time you sign in.' : '8+ characters, with a letter and a number.'}
    >
      {error && <RecoveryError message={error} />}
      {recovery.callback === 'pending' ? <p role="status">Verifying your recovery link…</p>
        : recovery.recovery === 'complete' ? <>
          <div className="recovery-acknowledgement" role="status"><p>Your password was updated successfully. This action has not signed you out.</p></div>
          <Link className="login-submit auth-planner-action" to="/login">Return to sign in</Link>
        </>
          : recovery.recovery === 'locked' ? <><RecoveryError message={recovery.error ?? 'A verified recovery link is required. Opening this page or signing in normally does not authorize a password reset.'} /><Link className="login-submit auth-planner-action" to="/forgot-password">Request a new recovery link</Link></>
            : <form onSubmit={handleSubmit} noValidate className="login-form" aria-busy={loading}>
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
      </form>}
    </PasswordRecoveryLayout>
  )
}
