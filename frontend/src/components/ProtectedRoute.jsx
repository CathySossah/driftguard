import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

/**
 * Protège une route : redirige vers /login si non connecté, et vers la page
 * d'accueil appropriée si le rôle ne correspond pas (ex. un utilisateur qui
 * essaie d'accéder à une page admin).
 */
export default function ProtectedRoute({ children, adminOnly = false }) {
  const { user, isAdmin } = useAuth()

  if (!user) return <Navigate to="/login" replace />
  if (adminOnly && !isAdmin) return <Navigate to="/home" replace />

  return children
}
