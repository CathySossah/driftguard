import { useEffect, useState, useCallback } from 'react'
import api from '../api/client'

export default function Models() {
  const [versions, setVersions] = useState([])
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [retryingId, setRetryingId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    const [vRes, jRes] = await Promise.all([
      api.get('/models/'),
      api.get('/retraining-jobs/'),
    ])
    setVersions(vRes.data.sort((a, b) => b.version_number - a.version_number))
    setJobs(jRes.data)
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  async function handleRetry(jobId) {
    setRetryingId(jobId)
    try {
      await api.post(`/retraining-jobs/${jobId}/retry`)
      await load()
    } finally {
      setRetryingId(null)
    }
  }

  if (loading) return <div className="page-loading"><span className="spinner" /> Chargement...</div>

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Gestion des modèles</h1>
          <div className="subtitle">Versions suivies via MLflow</div>
        </div>
      </div>

      <div className="card">
        {versions.length === 0 ? (
          <div className="empty-state">
            <h3>Aucun modèle</h3>
            <p>Aucune version de modèle n'a encore été créée.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Version</th><th>Statut</th><th>Précision</th><th>F1-score</th><th>Déployé le</th><th>MLflow</th></tr>
              </thead>
              <tbody>
                {versions.map((v) => (
                  <tr key={v.id}>
                    <td>v{v.version_number}</td>
                    <td>{v.status === 'en_production'
                      ? <span className="badge ok">En production</span>
                      : <span className="badge pending">{v.status}</span>}
                    </td>
                    <td>{v.metrics?.accuracy ? `${(v.metrics.accuracy * 100).toFixed(1)}%` : '—'}</td>
                    <td>{v.metrics?.f1 ?? '—'}</td>
                    <td>{v.deployed_at ? new Date(v.deployed_at).toLocaleDateString('fr-FR') : '—'}</td>
                    <td>
                      {v.mlflow_run_id ? (
                        <span className="muted" title={v.mlflow_run_id}>{v.mlflow_run_id.slice(0, 8)}...</span>
                      ) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card section-gap">
        <h3>Historique des ré-entraînements</h3>
        {jobs.length === 0 ? (
          <p className="muted" style={{ fontSize: 13 }}>Aucun ré-entraînement lancé pour l'instant.</p>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Déclenché le</th><th>Statut</th><th>Résultat</th></tr></thead>
                <tbody>
                  {jobs.filter((j) => j.status !== 'echoue').map((j) => (
                    <tr key={j.id}>
                      <td>{new Date(j.started_at).toLocaleString('fr-FR')}</td>
                      <td>
                        {j.status === 'reussi' && <span className="badge ok">Réussi</span>}
                        {j.status === 'en_cours' && <span className="badge pending">En cours</span>}
                      </td>
                      <td className="muted">{j.new_model_version_id ? 'Nouvelle version publiée' : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {jobs.filter((j) => j.status === 'echoue').map((j) => (
              <div className="fail-row section-gap" key={j.id}>
                <div className="fail-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16h.01" />
                  </svg>
                </div>
                <div style={{ flex: 1 }}>
                  <div className="fail-title">
                    Échec du ré-entraînement — {new Date(j.started_at).toLocaleString('fr-FR')}
                  </div>
                  <div className="fail-msg">{j.error_message}</div>
                  <button
                    className="btn-sm"
                    style={{ marginTop: 10, borderColor: 'var(--gold)', color: '#9c7419' }}
                    disabled={retryingId === j.id}
                    onClick={() => handleRetry(j.id)}
                  >
                    {retryingId === j.id ? 'Relance en cours...' : 'Relancer manuellement'}
                  </button>
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
