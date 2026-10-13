import { createContext, useContext, useState, useCallback } from 'react'
import api from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const stored = localStorage.getItem('driftguard_user')
    return stored ? JSON.parse(stored) : null
  })
  const [loading, setLoading] = useState(false)

  const login = useCallback(async (email, password) => {
    setLoading(true)
    try {
      const { data } = await api.post('/auth/login', { email, password })
      localStorage.setItem('driftguard_token', data.access_token)
      const me = await api.get('/users/me')
      localStorage.setItem('driftguard_user', JSON.stringify(me.data))
      setUser(me.data)
      return me.data
    } finally {
      setLoading(false)
    }
  }, [])

  const register = useCallback(async (fullName, email, password, role, adminCode) => {
    setLoading(true)
    try {
      await api.post('/auth/register', {
        full_name: fullName, email, password, role,
        admin_code: role === 'admin' ? adminCode : undefined,
      })
    } finally {
      setLoading(false)
    }
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('driftguard_token')
    localStorage.removeItem('driftguard_user')
    setUser(null)
  }, [])

  const isAdmin = user?.role === 'admin'

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, isAdmin }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth doit être utilisé à l\'intérieur de <AuthProvider>')
  return ctx
}
