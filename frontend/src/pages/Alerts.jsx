import { useEffect, useState, useCallback } from 'react'
import api from '../api/client'

export default function Alerts() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [actingId, setActingId] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/alerts/')
      setAlerts(data)
    } catch {
      setError('Impossible de charger les alertes.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleReview(alertId, approve) {
    setActingId(alertId)
    setError(null)
    try {
      await api.patch(`/alerts/${alertId}/review`, {
        approve,
        comment: approve ? 'Validée depuis le tableau de bord' : 'Rejetée depuis le tableau de bord',
      })
      await load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Action impossible.')
    } finally {
      setActingId(null)
    }
  }

  const statusBadge = (status) => {
    if (status === 'en_attente') return <span className="badge pending">En attente</span>
    if (status === 'validee') return <span className="badge ok">Validée</span>
    if (status === 'rejetee') return <span className="badge danger">Rejetée</span>
    return <span className="badge pending">{status}</span>
  }

  const severityBadge = (severity) => {
    const cls = severity === 'critique' ? 'danger' : severity === 'moyenne' ? 'warn' : 'pending'
    return <span className={`badge ${cls}`} style={{ textTransform: 'capitalize' }}>{severity}</span>
  }

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Gestion des alertes</h1>
          <div className="subtitle">Validation humaine requise avant tout ré-entraînement</div>
        </div>
      </div>

      {error && <div className="auth-error">{error}</div>}

      <div className="card">
        {loading ? (
          <div className="page-loading"><span className="spinner" /> Chargement...</div>
        ) : alerts.length === 0 ? (
          <div className="empty-state">
            <h3>Aucune alerte</h3>
            <p>Les alertes apparaîtront ici dès qu'une dérive dépassera le seuil configuré.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Déclenchée le</th><th>Sévérité</th><th>Statut</th><th>Action</th></tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.id}>
                    <td>{new Date(a.triggered_at).toLocaleString('fr-FR')}</td>
                    <td>{severityBadge(a.severity)}</td>
                    <td>{statusBadge(a.status)}</td>
                    <td>
                      {a.status === 'en_attente' ? (
                        <>
                          <button
                            className="btn-sm approve"
                            disabled={actingId === a.id}
                            onClick={() => handleReview(a.id, true)}
                          >
                            {actingId === a.id ? '...' : 'Valider'}
                          </button>
                          <button
                            className="btn-sm reject"
                            disabled={actingId === a.id}
                            onClick={() => handleReview(a.id, false)}
                          >
                            Rejeter
                          </button>
                        </>
                      ) : (
                        <span className="muted">
                          {a.status === 'validee' ? 'Ré-entraînement déclenché' : 'Aucune action'}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
