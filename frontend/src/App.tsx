import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import PlaceholderPage from './components/PlaceholderPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import LoginPage from './pages/LoginPage'
import OfflineDemoPage from './pages/OfflineDemoPage'
import ResultsPage from './pages/ResultsPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import SignupPage from './pages/SignupPage'
import TripPlannerPage from './pages/TripPlannerPage'
import WelcomePage from './pages/WelcomePage'
import AuthSessionProvider from './components/auth/AuthSessionProvider'
import EmailAuthProvider from './components/auth/EmailAuthProvider'

const AuthProbePage = import.meta.env.DEV ? lazy(() => import('./pages/dev/AuthProbePage')) : null

export default function App() {
  return (
    <Routes>
      <Route element={<EmailAuthProvider />}>
        <Route path="auth/callback" element={<PlaceholderPage title="Email link verification">Open a fresh email link to continue.</PlaceholderPage>} />
        <Route element={<AuthSessionProvider />}>
          {AuthProbePage && <Route path="dev/auth-probe" element={<Suspense fallback={<p role="status">Loading development tool…</p>}><AuthProbePage /></Suspense>} />}
          <Route path="/" element={<WelcomePage />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="signup" element={<SignupPage />} />
          <Route path="trip-planner" element={<TripPlannerPage />} />
          <Route path="results" element={<ResultsPage />} />
        </Route>
        <Route path="forgot-password" element={<ForgotPasswordPage />} />
        <Route path="reset-password" element={<ResetPasswordPage />} />
      </Route>
      <Route path="offline-demo" element={<OfflineDemoPage />} />
      <Route element={<AppLayout />}>
        <Route path="*" element={<PlaceholderPage title="Page not found">Use the navigation to return to a TravelMate page.</PlaceholderPage>} />
      </Route>
    </Routes>
  )
}
