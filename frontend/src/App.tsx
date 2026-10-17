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

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<WelcomePage />} />
      <Route path="login" element={<LoginPage />} />
      <Route path="signup" element={<SignupPage />} />
      <Route path="forgot-password" element={<ForgotPasswordPage />} />
      <Route path="reset-password" element={<ResetPasswordPage />} />
      <Route path="trip-planner" element={<TripPlannerPage />} />
      <Route path="results" element={<ResultsPage />} />
      <Route element={<AppLayout />}>
        <Route path="offline-demo" element={<OfflineDemoPage />} />
        <Route path="*" element={<PlaceholderPage title="Page not found">Use the navigation to return to a TravelMate page.</PlaceholderPage>} />
      </Route>
    </Routes>
  )
}
