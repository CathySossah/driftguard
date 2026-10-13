import { useEffect, useState, useCallback } from 'react'
import api from '../api/client'

export default function Monitoring() {
  const [versions, setVersions] = useState([])
  const [selectedVersionId, setSelectedVersionId] = useState('')
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)

  const loadVersions = useCallback(async () => {
    const { data } = await api.get('/models/')
    setVersions(data)
    const prod = data.find((v) => v.status === 'en_production') || data[0]
    if (prod) setSelectedVersionId(prod.id)
  }, [])

  useEffect(() => { loadVersions() }, [loadVersions])

  useEffect(() => {
    if (!selectedVersionId) return
    setLoading(true)
    api.get('/monitoring/', { params: { model_version_id: selectedVersionId } })
      .then(({ data }) => setRuns(data))
      .finally(() => setLoading(false))
  }, [selectedVersionId])

  const latestRun = runs[0]
  const columns = latestRun?.report_json?.columns || {}

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Monitoring détaillé</h1>
          <div className="subtitle">Comparaison distribution d'entraînement vs production — Evidently AI</div>
        </div>
        {versions.length > 0 && (
          <select
            className="field"
            style={{ margin: 0, minWidth: 180 }}
            value={selectedVersionId}
            onChange={(e) => setSelectedVersionId(e.target.value)}
          >
            {versions.map((v) => (
              <option key={v.id} value={v.id}>v{v.version_number} — {v.status}</option>
            ))}
          </select>
        )}
      </div>

      <div className="card">
        <h3>Dérive par variable (dernier run)</h3>
        {!latestRun ? (
          <p className="muted" style={{ fontSize: 13 }}>Aucun run de monitoring pour cette version.</p>
        ) : Object.keys(columns).length === 0 ? (
          <p className="muted" style={{ fontSize: 13 }}>Ce run ne contient pas de détail par variable.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Variable</th><th>Méthode</th><th>p-value</th><th>Statut</th></tr></thead>
              <tbody>
                {Object.entries(columns).map(([name, detail]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td className="muted">{detail.method}</td>
                    <td>{detail.p_value.toFixed(4)}</td>
                    <td>{detail.drifted
                      ? <span className="badge danger">Dérive détectée</span>
                      : <span className="badge ok">Stable</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card section-gap">
        <h3>Historique des exécutions</h3>
        {loading ? (
          <div className="page-loading"><span className="spinner" /> Chargement...</div>
        ) : runs.length === 0 ? (
          <p className="muted" style={{ fontSize: 13 }}>Aucune exécution enregistrée.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Score global</th><th>Dérive détectée</th></tr></thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>{new Date(r.executed_at).toLocaleString('fr-FR')}</td>
                    <td>{r.drift_score.toFixed(3)}</td>
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
  )
}
