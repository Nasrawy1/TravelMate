import { useLayoutEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import RivieraLogo from '../components/welcome/RivieraLogo'
import '../styles/trip-planner.css'
import '../styles/not-found.css'

/** Neutral navigation keeps unknown routes independent of hosted Auth initialization. */
export default function NotFoundPage() {
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  return <div className="trip-planner not-found">
    <a className="skip-link" href="#not-found">Skip to content</a>
    <header className="tp-header"><div className="tp-container tp-header-inner">
      <RivieraLogo />
      <nav aria-label="Main navigation" className="tp-nav"><Link to="/">Home</Link><Link to="/trip-planner">Plan a trip</Link></nav>
    </div></header>
    <main className="tp-container nf-main" id="not-found" tabIndex={-1}>
      <svg width="180" height="180" viewBox="0 0 180 180" aria-hidden="true">
        <defs><clipPath id="not-found-clip"><circle cx="90" cy="90" r="88" /></clipPath></defs>
        <g clipPath="url(#not-found-clip)"><circle cx="90" cy="90" r="88" fill="#EFD9C2" /><circle cx="90" cy="72" r="38" fill="#E9A15A" /><path d="M0 104c22-9 44-9 66 0s44 9 66 0 34-7 48-3v80H0z" fill="#2C5C8A" /><path d="M0 124c22-8 44-8 66 0s44 8 66 0 34-6 48-2" stroke="#EFD9C2" strokeWidth="4" fill="none" /></g>
      </svg>
      <p className="nf-eyebrow">Error 404 · Page not found</p>
      <h1 ref={heading} tabIndex={-1}>We can’t find that page</h1>
      <p>The link may be old or mistyped. Let’s get you back on route.</p>
      <div className="nf-actions"><Link className="nf-primary" to="/">Go to home</Link><Link className="nf-secondary" to="/trip-planner">Plan a trip</Link></div>
    </main>
  </div>
}
