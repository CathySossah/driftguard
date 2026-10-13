import { useEffect, useState, useCallback } from 'react'
import api from '../api/client'

function Gauge({ score }) {
  const clamped = Math.max(0, Math.min(1, score ?? 0))
  const angle = -90 + clamped * 180
  return (
    <div className="gauge-wrap">
      <svg width="200" height="120" viewBox="0 0 200 120">
        <path d="M 15 105 A 85 85 0 0 1 62 25" stroke="#2F9E63" strokeWidth="16" fill="none" strokeLinecap="round" />
        <path d="M 66 22 A 85 85 0 0 1 134 22" stroke="#D98C1F" strokeWidth="16" fill="none" strokeLinecap="round" />
        <path d="M 138 25 A 85 85 0 0 1 185 105" stroke="#D1483F" strokeWidth="16" fill="none" strokeLinecap="round" />
        <g transform={`rotate(${angle} 100 105)`}>
          <line x1="100" y1="105" x2="100" y2="32" stroke="#1E2A44" strokeWidth="3" strokeLinecap="round" />
        </g>
        <circle cx="100" cy="105" r="6" fill="#1E2A44" />
      </svg>
      <div className="gauge-value">{score != null ? score.toFixed(2) : '—'}</div>
      <div className="gauge-caption">Seuil critique : 0.60</div>
      <div className="legend">
        <span><i className="dot" style={{ background: '#2F9E63' }} />Stable</span>
        <span><i className="dot" style={{ background: '#D98C1F' }} />Surveillance</span>
        <span><i className="dot" style={{ background: '#D1483F' }} />Dérive</span>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [version, setVersion] = useState(null)
  const [runs, setRuns] = useState([])
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const [error, setError] = useState(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const versionsRes = await api.get('/models/')
      const prodVersion = versionsRes.data.find((v) => v.status === 'en_production') || versionsRes.data[0]
      setVersion(prodVersion || null)

      if (prodVersion) {
        const [runsRes, alertsRes] = await Promise.all([
          api.get('/monitoring/', { params: { model_version_id: prodVersion.id } }),
          api.get('/alerts/'),
        ])
        setRuns(runsRes.data)
        setAlerts(alertsRes.data)
      }
    } catch {
      setError('Impossible de charger les données du tableau de bord. Le serveur est-il démarré ?')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  async function handleRunNow() {
    if (!version) return
    setTriggering(true)
    try {
      await api.post(`/monitoring/run-now/${version.id}`)
      await loadData()
    } catch {
      setError('Le cycle de monitoring a échoué.')
    } finally {
      setTriggering(false)
    }
  }

  if (loading) return <div className="page-loading"><span className="spinner" /> Chargement du tableau de bord...</div>
  if (error) return <div className="auth-error">{error}</div>

  if (!version) {
    return (
      <div className="empty-state card">
        <h3>Aucun modèle en production</h3>
        <p>Crée un dataset et une version de modèle (via l'API ou le seed de démonstration) pour voir apparaître le tableau de bord.</p>
      </div>
    )
  }

  const latestRun = runs[0]
  const activeAlerts = alerts.filter((a) => a.status === 'en_attente')
  const lastRetrainDays = version.deployed_at
    ? Math.round((Date.now() - new Date(version.deployed_at)) / 86400000)
    : null

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Tableau de bord</h1>
          <div className="subtitle">Modèle en production — v{version.version_number}</div>
        </div>
        <button className="btn-outline" onClick={handleRunNow} disabled={triggering}>
          {triggering ? 'Calcul en cours...' : 'Lancer un cycle de monitoring'}
        </button>
      </div>

      <div className="grid grid-4">
        <div className="card kpi">
          <div className="label">Score de dérive</div>
          <div className="value">{latestRun ? latestRun.drift_score.toFixed(2) : '—'}</div>
          <div className={`delta ${latestRun?.drift_detected ? 'down' : 'up'}`}>
            {latestRun ? (latestRun.drift_detected ? 'Dérive détectée' : 'Sous le seuil') : 'Aucun run encore'}
          </div>
        </div>
        <div className="card kpi">
          <div className="label">Précision du modèle</div>
          <div className="value">{version.metrics?.accuracy ? `${(version.metrics.accuracy * 100).toFixed(1)}%` : '—'}</div>
        </div>
        <div className="card kpi">
          <div className="label">Alertes actives</div>
          <div className="value">{activeAlerts.length}</div>
          <div className="delta">{activeAlerts.length > 0 ? 'En attente de validation' : 'Aucune'}</div>
        </div>
        <div className="card kpi">
          <div className="label">Dernier déploiement</div>
          <div className="value">{lastRetrainDays != null ? `${lastRetrainDays} j` : '—'}</div>
        </div>
      </div>

      <div className="grid grid-2 section-gap">
        <div className="card">
          <h3>Jauge du score de dérive</h3>
          <Gauge score={latestRun?.drift_score} />
        </div>

        <div className="card">
          <h3>Historique des runs de monitoring</h3>
          {runs.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>Aucun cycle de monitoring exécuté pour l'instant.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Date</th><th>Score</th><th>Dérive</th></tr>
                </thead>
                <tbody>
                  {runs.slice(0, 6).map((r) => (
                    <tr key={r.id}>
                      <td>{new Date(r.executed_at).toLocaleString('fr-FR')}</td>
                      <td>{r.drift_score.toFixed(2)}</td>
                      <td>{r.drift_detected
                        ? <span className="badge danger">Oui</span>
                        : <span className="badge ok">Non</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div className="card section-gap">
        <h3>Alertes récentes</h3>
        {alerts.length === 0 ? (
          <p className="muted" style={{ fontSize: 13 }}>Aucune alerte pour le moment.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Sévérité</th><th>Statut</th></tr></thead>
              <tbody>
                {alerts.slice(0, 5).map((a) => (
                  <tr key={a.id}>
                    <td style={{ textTransform: 'capitalize' }}>{a.severity}</td>
                    <td>
                      {a.status === 'en_attente' && <span className="badge pending">En attente</span>}
                      {a.status === 'validee' && <span className="badge ok">Validée</span>}
                      {a.status === 'rejetee' && <span className="badge danger">Rejetée</span>}
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
