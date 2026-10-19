import { Link } from 'react-router-dom'
import { useAuthSessionState } from './AuthSessionProvider'

export default function AuthNavigationLink() {
  const { status } = useAuthSessionState()
  if (status === 'checking') return <span role="status">Checking session…</span>
  return <Link to="/login">{status === 'authenticated' ? 'My account' : 'Sign in'}</Link>
}
