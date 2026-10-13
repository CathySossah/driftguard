import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'

import Login from './pages/Login'
import Signup from './pages/Signup'
import Dashboard from './pages/Dashboard'
import Datasets from './pages/Datasets'
import Monitoring from './pages/Monitoring'
import Alerts from './pages/Alerts'
import Models from './pages/Models'
import CompareModels from './pages/CompareModels'
import Users from './pages/Users'
import Settings from './pages/Settings'
import Audit from './pages/Audit'
import UserHome from './pages/UserHome'
import UserPredict from './pages/UserPredict'
import UserHistory from './pages/UserHistory'

function RoleHome() {
  const { isAdmin } = useAuth()
  return <Navigate to={isAdmin ? '/dashboard' : '/home'} replace />
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
            <Route path="/" element={<RoleHome />} />

            {/* Espace administrateur */}
            <Route path="/dashboard" element={<ProtectedRoute adminOnly><Dashboard /></ProtectedRoute>} />
            <Route path="/datasets" element={<ProtectedRoute adminOnly><Datasets /></ProtectedRoute>} />
            <Route path="/monitoring" element={<ProtectedRoute adminOnly><Monitoring /></ProtectedRoute>} />
            <Route path="/alerts" element={<ProtectedRoute adminOnly><Alerts /></ProtectedRoute>} />
            <Route path="/models" element={<ProtectedRoute adminOnly><Models /></ProtectedRoute>} />
            <Route path="/compare" element={<ProtectedRoute adminOnly><CompareModels /></ProtectedRoute>} />
            <Route path="/users" element={<ProtectedRoute adminOnly><Users /></ProtectedRoute>} />
            <Route path="/settings" element={<ProtectedRoute adminOnly><Settings /></ProtectedRoute>} />
            <Route path="/audit" element={<ProtectedRoute adminOnly><Audit /></ProtectedRoute>} />

            {/* Espace utilisateur */}
            <Route path="/home" element={<UserHome />} />
            <Route path="/predict" element={<UserPredict />} />
            <Route path="/history" element={<UserHistory />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
