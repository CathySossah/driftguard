import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'

function initials(name = '') {
  return name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase()
}

export default function Users() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  const load = useCallback(async () => {
    setLoading(true)
    const { data } = await api.get('/users/')
    setUsers(data)
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  async function handleDeactivate(userId) {
    await api.patch(`/users/${userId}/deactivate`)
    await load()
  }

  if (loading) return <div className="page-loading"><span className="spinner" /> Chargement...</div>

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Gestion des utilisateurs</h1>
          <div className="subtitle">Comptes ayant accès à la plateforme</div>
        </div>
      </div>

      <div className="grid grid-3">
        {users.map((u) => (
          <div className="card" key={u.id} style={{ textAlign: 'center' }}>
            <div className="avatar" style={{ width: 56, height: 56, fontSize: 18, margin: '0 auto 12px' }}>
              {initials(u.full_name)}
            </div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>{u.full_name}</div>
            {u.role === 'admin'
              ? <span className="badge ok">Administrateur</span>
              : <span className="badge pending">Utilisateur</span>}
            <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--border)', textAlign: 'left' }}>
              <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>{u.email}</div>
              <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
                Membre depuis le {new Date(u.created_at).toLocaleDateString('fr-FR')}
              </div>
              <div className="muted" style={{ fontSize: 12 }}>
                {u.is_active ? 'Compte actif' : 'Compte désactivé'}
              </div>
            </div>
            {u.is_active && (
              <button
                className="btn-sm reject"
                style={{ marginTop: 14, width: '100%' }}
                onClick={() => handleDeactivate(u.id)}
              >
                Désactiver
              </button>
            )}
          </div>
        ))}
      </div>

      <div className="card section-gap" style={{ textAlign: 'center', padding: '1.5rem' }}>
        <button className="btn-gold" onClick={() => navigate('/signup')}>+ Ajouter un utilisateur</button>
      </div>
    </div>
  )
}
