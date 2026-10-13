import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const { login, loading } = useAuth()
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    try {
      const user = await login(email, password)
      navigate(user.role === 'admin' ? '/dashboard' : '/home')
    } catch (err) {
      setError(err.response?.data?.detail || 'Impossible de se connecter. Vérifie tes identifiants.')
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="brand">Drift<span>Guard</span></div>
        <div className="tagline">MONITORING &amp; FIABILITÉ DES MODÈLES ML</div>

        {error && <div className="auth-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label>Adresse e-mail</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="field">
            <label>Mot de passe</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </div>
          <button className="btn-gold" style={{ width: '100%' }} disabled={loading}>
            {loading ? 'Connexion...' : 'Se connecter'}
          </button>
        </form>

        <div className="auth-switch">
          Pas encore de compte ? <Link to="/signup">Créer un compte</Link>
        </div>
      </div>
    </div>
  )
}
