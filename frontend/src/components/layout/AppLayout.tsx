import { NavLink, Outlet } from 'react-router-dom'
import type { NavigationItem } from '../../types/navigation'

const navigation: NavigationItem[] = [
  { label: 'Welcome', path: '/' },
  { label: 'Login', path: '/login' },
  { label: 'Signup', path: '/signup' },
  { label: 'Forgot Password', path: '/forgot-password' },
  { label: 'Trip Planner', path: '/trip-planner' },
  { label: 'Results', path: '/results' },
  { label: 'Offline Demo', path: '/offline-demo' },
]

export default function AppLayout() {
  return (
    <div className="app-layout">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="site-header">
        <span className="site-name">TravelMate</span>
        <nav aria-label="Main navigation">
          <ul>
            {navigation.map(({ label, path }) => (
              <li key={path}>
                <NavLink to={path} end={path === '/'}>{label}</NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main-content" tabIndex={-1}>
        <Outlet />
      </main>
      <footer>FE-01 foundation · Page designs pending approval.</footer>
    </div>
  )
}
