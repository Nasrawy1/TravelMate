import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import RivieraLogo from '../welcome/RivieraLogo'
import '../../styles/welcome.css'
import '../../styles/login.css'
import '../../styles/password-recovery.css'

interface PasswordRecoveryLayoutProps {
  title: string
  description: string
  children: ReactNode
}

export default function PasswordRecoveryLayout({ title, description, children }: PasswordRecoveryLayoutProps) {
  return (
    <div className="welcome login-page recovery-page">
      <a className="skip-link" href="#recovery-content">Skip to password recovery form</a>
      <svg className="recovery-wave" viewBox="0 0 1440 260" preserveAspectRatio="none" aria-hidden="true">
        <path d="M0 90c120-40 240-40 360 0s240 40 360 0 240-40 360 0 240 40 360 0v170H0z" fill="#2C5C8A" />
        <path d="M0 150c120-35 240-35 360 0s240 35 360 0 240-35 360 0 240 35 360 0" stroke="#F6EBDD" strokeWidth="5" fill="none" />
      </svg>
      <header className="recovery-header welcome-container">
        <RivieraLogo />
        <Link to="/login" className="login-back-link"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M19 12H5M11 6l-6 6 6 6" /></svg>Back to sign in</Link>
      </header>
      <main id="recovery-content" className="recovery-main" tabIndex={-1}>
        <section className="recovery-card" aria-labelledby="recovery-title">
          <div className="recovery-heading"><h1 id="recovery-title">{title}</h1><p>{description}</p></div>
          {children}
        </section>
      </main>
    </div>
  )
}

export function RecoveryError({ message }: { message: string }) {
  return (
    <div className="login-error-banner" role="alert">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5M12 16.5v.5" /></svg>
      <p>{message}</p>
    </div>
  )
}

export function RecoverySubmitButton({ loading, label, loadingLabel }: { loading: boolean; label: string; loadingLabel: string }) {
  return (
    <button type="submit" className="login-submit" disabled={loading}>
      {loading && <svg className="login-spinner" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M12 3a9 9 0 1 0 9 9" /></svg>}
      <span aria-live="polite">{loading ? loadingLabel : label}</span>
    </button>
  )
}
