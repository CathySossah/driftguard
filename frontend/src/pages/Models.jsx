import { useEffect, useState, useCallback } from 'react'
import api from '../api/client'
import { MODEL_STATUSES, statusInfo } from '../utils/modelStatus'
import { errorMessage } from '../utils/prediction'

export default function Models() {
  const [versions, setVersions] = useState([])
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [retryingId, setRetryingId] = useState(null)
  const [datasetNames, setDatasetNames] = useState({})
  const [statusFilter, setStatusFilter] = useState('')
  const [changingId, setChangingId] = useState(null)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    const [vRes, jRes, dRes] = await Promise.all([
      api.get('/models/'),
      api.get('/retraining-jobs/'),
      api.get('/datasets/'),
    ])
    setVersions(vRes.data.sort((a, b) => b.version_number - a.version_number))
    setJobs(jRes.data)
    setDatasetNames(Object.fromEntries(dRes.data.map((d) => [d.id, d.name])))
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

  // Actions possibles selon le statut actuel
  function actionsFor(version) {
    switch (version.status) {
      case 'en_test':
        return [['staging', 'Passer en staging'], ['en_production', 'Mettre en production'], ['archive', 'Archiver']]
      case 'staging':
        return [['en_production', 'Mettre en production'], ['archive', 'Archiver']]
      case 'en_production':
        return [['staging', 'Rétrograder en staging'], ['archive', 'Archiver']]
      default:
        return [['staging', 'Remettre en staging'], ['en_production', 'Mettre en production']]
    }
  }

  async function changeStatus(version, status) {
    const current = versions.find((v) => v.dataset_id === version.dataset_id && v.status === 'en_production')
    let question = null
    if (status === 'en_production' && current && current.id !== version.id) {
      question = `Mettre la v${version.version_number} en production archivera la v${current.version_number}, actuellement en production pour ce dataset. Continuer ?`
    } else if (version.status === 'en_production') {
      question = `Aucun modèle ne sera plus en production pour ce dataset : les utilisateurs ne pourront plus faire de prédictions. Continuer ?`
    }
    if (question && !window.confirm(question)) return

    setChangingId(version.id)
    setError(null)
    setSuccess(null)
    try {
      await api.patch(`/models/${version.id}/status`, { status })
      setSuccess(`Version v${version.version_number} : nouveau statut « ${statusInfo(status).label} ».`)
      await load()
    } catch (err) {
      setError(errorMessage(err, 'Le changement de statut a échoué.'))
    } finally {
      setChangingId(null)
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

      {error && <div className="auth-error">{error}</div>}
      {success && <div className="auth-error" style={{ background: 'var(--success-bg)', color: 'var(--success)' }}>{success}</div>}

      <div className="card">
        <h3>Statuts d'une version</h3>
        <div className="grid grid-4">
          {MODEL_STATUSES.map((st) => (
            <div key={st.key}>
              <span className={`badge ${st.badge}`}>{st.label}</span>
              <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>{st.help}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="card section-gap">
        <div className="field" style={{ maxWidth: 240 }}>
          <label>Filtrer par statut</label>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">Tous les statuts</option>
            {MODEL_STATUSES.map((st) => <option key={st.key} value={st.key}>{st.label}</option>)}
          </select>
        </div>
        {versions.length === 0 ? (
          <div className="empty-state">
            <h3>Aucun modèle</h3>
            <p>Aucune version de modèle n'a encore été créée.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Version</th><th>Dataset</th><th>Statut</th><th>Précision</th><th>F1-score</th><th>Déployé le</th><th>MLflow</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {versions.filter((v) => !statusFilter || v.status === statusFilter).map((v) => (
                  <tr key={v.id}>
                    <td>v{v.version_number}</td>
                    <td>{datasetNames[v.dataset_id] || '—'}</td>
                    <td><span className={`badge ${statusInfo(v.status).badge}`}>{statusInfo(v.status).label}</span></td>
                    <td>{v.metrics?.accuracy ? `${(v.metrics.accuracy * 100).toFixed(1)}%` : '—'}</td>
                    <td>{v.metrics?.f1 ?? '—'}</td>
                    <td>{v.deployed_at ? new Date(v.deployed_at).toLocaleDateString('fr-FR') : '—'}</td>
                    <td>
                      {v.mlflow_run_id ? (
                        <span className="muted" title={v.mlflow_run_id}>{v.mlflow_run_id.slice(0, 8)}...</span>
                      ) : '—'}
                    </td>
                    <td>
                      {actionsFor(v).map(([status, label]) => (
                        <button
                          key={status}
                          className={`btn-sm ${status === 'en_production' ? 'approve' : ''}`}
                          disabled={changingId === v.id}
                          onClick={() => changeStatus(v, status)}
                        >
                          {label}
                        </button>
                      ))}
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
