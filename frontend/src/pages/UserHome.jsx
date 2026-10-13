import { useEffect, useState } from 'react'
import api from '../api/client'
import { useAuth } from '../context/AuthContext'

export default function UserHome() {
  const { user } = useAuth()
  const [version, setVersion] = useState(null)
  const [latestRun, setLatestRun] = useState(null)
  const [predictionCount, setPredictionCount] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const versionsRes = await api.get('/models/')
      const prod = versionsRes.data.find((v) => v.status === 'en_production') || versionsRes.data[0]
      setVersion(prod || null)

      if (prod) {
        const runsRes = await api.get('/monitoring/', { params: { model_version_id: prod.id } })
        setLatestRun(runsRes.data[0] || null)
      }

      const historyRes = await api.get('/predictions/history')
      setPredictionCount(historyRes.data.length)
      setLoading(false)
    }
    load()
  }, [])

  if (loading) return <div className="page-loading"><span className="spinner" /> Chargement...</div>

  const isHealthy = !latestRun?.drift_detected

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Bonjour {user?.full_name?.split(' ')[0]}</h1>
          <div className="subtitle">Voici l'état actuel du modèle de détection de fraude</div>
        </div>
      </div>

      <div className={`health-banner ${isHealthy ? 'ok' : ''}`} style={{
        display: 'flex', alignItems: 'center', gap: '1.2rem', padding: '1.5rem', borderRadius: 10, marginBottom: '1.5rem',
        background: isHealthy ? 'var(--success-bg)' : 'var(--danger-bg)',
        border: `1px solid ${isHealthy ? '#cdeadc' : '#f0c9c6'}`,
      }}>
        <div style={{ width: 14, height: 14, borderRadius: '50%', background: isHealthy ? 'var(--success)' : 'var(--danger)', flexShrink: 0 }} />
        <div>
          <h2 style={{ fontSize: 17, fontWeight: 600, fontFamily: 'Inter, sans-serif' }}>
            {isHealthy ? 'Modèle fiable' : 'Modèle sous surveillance'}
          </h2>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 3 }}>
            {latestRun
              ? `Dernière vérification le ${new Date(latestRun.executed_at).toLocaleString('fr-FR')}`
              : 'Aucune vérification effectuée pour l\'instant'}
          </p>
        </div>
      </div>

      <div className="grid grid-4">
        <div className="card kpi">
          <div className="label">Précision actuelle</div>
          <div className="value">{version?.metrics?.accuracy ? `${(version.metrics.accuracy * 100).toFixed(1)}%` : '—'}</div>
        </div>
        <div className="card kpi">
          <div className="label">Version en service</div>
          <div className="value">v{version?.version_number ?? '—'}</div>
        </div>
        <div className="card kpi">
          <div className="label">Vos prédictions</div>
          <div className="value">{predictionCount}</div>
        </div>
        <div className="card kpi">
          <div className="label">Statut</div>
          <div className="value">{isHealthy ? 'OK' : 'Alerte'}</div>
        </div>
      </div>
    </div>
  )
}
