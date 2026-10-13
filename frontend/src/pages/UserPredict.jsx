import { useEffect, useState } from 'react'
import api from '../api/client'
import { predictionDisplay, errorMessage } from '../utils/prediction'

export default function UserPredict() {
  const [models, setModels] = useState([])
  const [versionId, setVersionId] = useState('')
  const [schema, setSchema] = useState(null)
  const [values, setValues] = useState({})
  const [result, setResult] = useState(null)
  const [loadingModels, setLoadingModels] = useState(true)
  const [loadingSchema, setLoadingSchema] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/predictions/models')
      .then(({ data }) => {
        setModels(data)
        if (data[0]) setVersionId(data[0].id)
      })
      .catch((err) => setError(errorMessage(err, 'Impossible de charger les modèles disponibles.')))
      .finally(() => setLoadingModels(false))
  }, [])

  useEffect(() => {
    if (!versionId) return undefined
    let cancelled = false
    setLoadingSchema(true)
    setSchema(null)
    setResult(null)
    setError(null)
    api.get(`/predictions/schema/${versionId}`)
      .then(({ data }) => {
        if (cancelled) return
        setSchema(data)
        setValues(Object.fromEntries(data.fields.map((f) => [f.name, String(f.default)])))
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, 'Impossible de charger le formulaire de ce modèle.'))
      })
      .finally(() => {
        if (!cancelled) setLoadingSchema(false)
      })
    return () => { cancelled = true }
  }, [versionId])

  async function handleSubmit(e) {
    e.preventDefault()
    if (!schema) return
    setSubmitting(true)
    setError(null)
    try {
      const payload = {}
      for (const f of schema.fields) {
        payload[f.name] = f.type === 'number' ? Number(values[f.name]) : values[f.name]
      }
      const { data } = await api.post('/predictions/', { model_version_id: versionId, input_payload: payload })
      setResult(data)
    } catch (err) {
      setResult(null)
      setError(errorMessage(err, 'La prédiction a échoué.'))
    } finally {
      setSubmitting(false)
    }
  }

  if (loadingModels) return <div className="page-loading"><span className="spinner" /> Chargement...</div>

  const display = result ? predictionDisplay(result.prediction) : null
  const contributions = result?.shap_explanation ? Object.entries(result.shap_explanation) : []

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Faire une prédiction</h1>
          <div className="subtitle">
            {schema ? `Modèle v${schema.version_number} — ${schema.dataset_name}` : 'Interroger le modèle en production'}
          </div>
        </div>
      </div>

      {error && <div className="auth-error">{error}</div>}

      {models.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <h3>Aucun modèle disponible</h3>
            <p>Un administrateur doit d'abord entraîner un modèle avant que vous puissiez faire une prédiction.</p>
          </div>
        </div>
      ) : (
        <div className="card">
          {models.length > 1 && (
            <div className="field">
              <label>Modèle</label>
              <select value={versionId} onChange={(e) => setVersionId(e.target.value)}>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>v{m.version_number} — {m.dataset_name}</option>
                ))}
              </select>
            </div>
          )}

          {loadingSchema && <div className="page-loading"><span className="spinner" /> Chargement du formulaire...</div>}

          {schema && (
            <form onSubmit={handleSubmit}>
              <div className="grid grid-2">
                {schema.fields.map((f) => (
                  <div className="field" key={f.name}>
                    <label>{f.name}</label>
                    {f.type === 'category' ? (
                      <select value={values[f.name] ?? ''} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}>
                        {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : (
                      <input
                        type="number" step="any" required
                        value={values[f.name] ?? ''}
                        onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                      />
                    )}
                  </div>
                ))}
              </div>
              <button className="btn-gold" disabled={submitting}>
                {submitting ? 'Calcul en cours...' : 'Lancer la prédiction'}
              </button>
            </form>
          )}

          {result && (
            <>
              <div className="result-box" style={{
                background: 'var(--gold-softer)', border: '1px solid var(--gold-soft)', borderRadius: 6,
                padding: '1rem', marginTop: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <div>
                  <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>Résultat</div>
                  <div style={{ fontSize: 20, fontWeight: 600, color: '#9c7419' }}>{display.title}</div>
                  {result.probability != null && (
                    <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 4 }}>
                      {result.probability_label} : <strong>{(result.probability * 100).toFixed(1)} %</strong>
                    </div>
                  )}
                </div>
                <span className={`badge ${display.cls}`}>{display.badge}</span>
              </div>

              {contributions.length > 0 && (
                <div className="explain-box">
                  <h3 style={{ marginBottom: '0.75rem' }}>Pourquoi ce résultat ?</h3>
                  {contributions.map(([feature, value]) => (
                    <div className="explain-item" key={feature}>
                      <span className="explain-dot" />
                      <span>
                        <strong>{feature}</strong> a {value > 0 ? 'augmenté' : 'diminué'} le score
                        de {Math.abs(value * 100).toFixed(1)} points.
                      </span>
                    </div>
                  ))}
                  <p className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>
                    Estimation obtenue en remplaçant chaque variable par une valeur typique du jeu d'entraînement.
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
