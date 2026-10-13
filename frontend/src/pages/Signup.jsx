import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Signup() {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState('user')
  const [adminCode, setAdminCode] = useState('')
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)
  const { register, loading } = useAuth()
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    try {
      await register(fullName, email, password, role, adminCode)
      setSuccess(true)
      setTimeout(() => navigate('/login'), 1200)
    } catch (err) {
      setError(err.response?.data?.detail || 'Impossible de créer le compte.')
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="brand">Drift<span>Guard</span></div>
        <div className="tagline">CRÉER UN COMPTE</div>

        {error && <div className="auth-error">{error}</div>}
        {success && <div className="auth-error" style={{ background: 'var(--success-bg)', color: 'var(--success)' }}>
          Compte créé avec succès — redirection vers la connexion...
        </div>}

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label>Nom complet</label>
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          </div>
          <div className="field">
            <label>Adresse e-mail</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="field">
            <label>Mot de passe</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
          </div>
          <div className="field">
            <label>Rôle</label>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="user">Utilisateur</option>
              <option value="admin">Administrateur</option>
            </select>
          </div>
          {role === 'admin' && (
            <div className="field">
              <label>Code d'invitation administrateur</label>
              <input type="password" value={adminCode} onChange={(e) => setAdminCode(e.target.value)} autoComplete="off" placeholder="Laisser vide si aucun code n'est configuré" />
            </div>
          )}
          <button className="btn-gold" style={{ width: '100%' }} disabled={loading}>
            {loading ? 'Création...' : 'Créer le compte'}
          </button>
        </form>

        <div className="auth-switch">
          Déjà un compte ? <Link to="/login">Se connecter</Link>
        </div>
      </div>
    </div>
  )
}
