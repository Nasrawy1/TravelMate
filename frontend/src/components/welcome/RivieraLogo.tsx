import { Link } from 'react-router-dom'

export default function RivieraLogo() {
  return (
    <Link to="/" className="welcome-logo" aria-label="TravelMate home">
      <svg width="36" height="36" viewBox="0 0 34 34" aria-hidden="true">
        <circle cx="17" cy="17" r="16" fill="#B14E2E" />
        <path d="M6 21c4-2 7-2 11 0s7 2 11 0" stroke="#F6EBDD" strokeWidth="2.4" fill="none" strokeLinecap="round" />
        <circle cx="17" cy="13" r="4" fill="#F6EBDD" />
      </svg>
      TravelMate
    </Link>
  )
}
