import { useEffect, useState, useCallback, useRef } from 'react'
import api from '../api/client'

const domainLabels = {
  finance: 'Finance',
  sante: 'Santé',
  agriculture: 'Agriculture',
}

export default function Datasets() {
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [preview, setPreview] = useState(null)
  const [configuring, setConfiguring] = useState(null) // dataset en cours de configuration
  const [targetCol, setTargetCol] = useState('')
  const [timeCol, setTimeCol] = useState('')
  const [savingConfig, setSavingConfig] = useState(false)
  const [trainingId, setTrainingId] = useState(null)

  const [file, setFile] = useState(null)
  const [name, setName] = useState('')
  const [domain, setDomain] = useState('finance')
  const fileInputRef = useRef(null)

  const load = useCallback(async () => {
    setLoading(true)
    const { data } = await api.get('/datasets/')
    setDatasets(data)
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  async function handleUpload(e) {
    e.preventDefault()
    if (!file) {
      setError('Choisis un fichier .csv avant d\'importer.')
      return
    }
    setUploading(true)
    setError(null)
    setSuccess(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('name', name || file.name)
      formData.append('domain', domain)

      const { data: created } = await api.post('/datasets/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      setSuccess('Dataset importé. Configure sa colonne cible ci-dessous pour pouvoir l\'utiliser.')
      setFile(null)
      setName('')
      if (fileInputRef.current) fileInputRef.current.value = ''
      await load()
      await handlePreview(created.id)
      openConfig(created)
    } catch (err) {
      setError(err.response?.data?.detail || 'L\'import a échoué.')
    } finally {
      setUploading(false)
    }
  }

  async function handlePreview(datasetId) {
    setPreview(null)
    try {
      const { data } = await api.get(`/datasets/${datasetId}/preview`)
      setPreview({ datasetId, ...data })
      return data
    } catch (err) {
      setError(err.response?.data?.detail || 'Impossible de charger l\'aperçu.')
    }
  }

  function openConfig(dataset) {
    setConfiguring(dataset)
    setTargetCol(dataset.target_column || '')
    setTimeCol(dataset.time_column || '')
    if (!preview || preview.datasetId !== dataset.id) handlePreview(dataset.id)
  }

  async function handleSaveConfig(e) {
    e.preventDefault()
    if (!targetCol) {
      setError('Choisis une colonne cible.')
      return
    }
    setSavingConfig(true)
    setError(null)
    try {
      await api.patch(`/datasets/${configuring.id}/configure`, {
        target_column: targetCol,
        time_column: timeCol || null,
      })
      setSuccess('Configuration enregistrée. Tu peux maintenant entraîner un modèle sur ce dataset.')
      setConfiguring(null)
      await load()
    } catch (err) {
      setError(err.response?.data?.detail || 'La configuration a échoué.')
    } finally {
      setSavingConfig(false)
    }
  }

  async function handleTrainInitial(datasetId) {
    setTrainingId(datasetId)
    setError(null)
    setSuccess(null)
    try {
      await api.post(`/models/train-initial/${datasetId}`)
      setSuccess('Entraînement lancé en tâche de fond sur les données réelles — consulte la page Modèles dans quelques instants.')
    } catch (err) {
      setError(err.response?.data?.detail || 'Impossible de lancer l\'entraînement.')
    } finally {
      setTrainingId(null)
    }
  }

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Datasets</h1>
          <div className="subtitle">Jeux de données utilisés pour l'entraînement et le monitoring</div>
        </div>
      </div>

      {error && <div className="auth-error">{error}</div>}
      {success && <div className="auth-error" style={{ background: 'var(--success-bg)', color: 'var(--success)' }}>{success}</div>}

      <div className="card">
        <h3>Importer un dataset</h3>
        <form onSubmit={handleUpload}>
          <div className="grid grid-3">
            <div className="field" style={{ margin: 0 }}>
              <label>Fichier CSV</label>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                onChange={(e) => setFile(e.target.files[0] || null)}
              />
            </div>
            <div className="field" style={{ margin: 0 }}>
              <label>Nom du dataset</label>
              <input
                type="text"
                placeholder="ex. IEEE-CIS Fraud Detection"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="field" style={{ margin: 0 }}>
              <label>Domaine</label>
              <select value={domain} onChange={(e) => setDomain(e.target.value)}>
                <option value="finance">Finance</option>
                <option value="sante">Santé</option>
                <option value="agriculture">Agriculture</option>
              </select>
            </div>
          </div>
          <button className="btn-gold section-gap" disabled={uploading}>
            {uploading ? 'Import en cours...' : 'Importer le dataset'}
          </button>
        </form>
        <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
          Après l'import, tu devras préciser quelle colonne du fichier est la cible à prédire
          (ex. <code>isFraud</code>, <code>readmitted</code>) avant de pouvoir entraîner un modèle.
        </p>
      </div>

      <div className="card section-gap">
        <h3>Datasets disponibles</h3>
        {loading ? (
          <div className="page-loading"><span className="spinner" /> Chargement...</div>
        ) : datasets.length === 0 ? (
          <div className="empty-state">
            <h3>Aucun dataset</h3>
            <p>Importe ton premier fichier CSV ci-dessus pour commencer.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Nom</th><th>Domaine</th><th>Colonne cible</th><th>Importé le</th><th></th></tr></thead>
              <tbody>
                {datasets.map((d) => (
                  <tr key={d.id}>
                    <td>{d.name}</td>
                    <td><span className="badge pending">{domainLabels[d.domain] || d.domain}</span></td>
                    <td>
                      {d.target_column
                        ? <span className="badge ok">{d.target_column}</span>
                        : <span className="badge warn">Non configurée</span>}
                    </td>
                    <td>{new Date(d.created_at).toLocaleDateString('fr-FR')}</td>
                    <td>
                      <button className="btn-sm" onClick={() => handlePreview(d.id)}>Aperçu</button>
                      <button className="btn-sm" onClick={() => openConfig(d)}>Configurer</button>
                      {d.target_column && (
                        <button
                          className="btn-sm approve"
                          disabled={trainingId === d.id}
                          onClick={() => handleTrainInitial(d.id)}
                        >
                          {trainingId === d.id ? 'Lancement...' : 'Entraîner un modèle'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {configuring && (
        <div className="card section-gap">
          <h3>Configurer — {configuring.name}</h3>
          <form onSubmit={handleSaveConfig}>
            <div className="grid grid-2">
              <div className="field" style={{ margin: 0 }}>
                <label>Colonne cible (à prédire)</label>
                <select value={targetCol} onChange={(e) => setTargetCol(e.target.value)} required>
                  <option value="">— Choisir —</option>
                  {(preview?.columns || []).map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label>Colonne temporelle (optionnel)</label>
                <select value={timeCol} onChange={(e) => setTimeCol(e.target.value)}>
                  <option value="">— Aucune (ordre du fichier) —</option>
                  {(preview?.columns || []).map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            </div>
            <button className="btn-gold section-gap" disabled={savingConfig}>
              {savingConfig ? 'Enregistrement...' : 'Enregistrer la configuration'}
            </button>
            <button
              type="button"
              className="btn-sm"
              style={{ marginLeft: 10 }}
              onClick={() => setConfiguring(null)}
            >
              Annuler
            </button>
          </form>
        </div>
      )}

      {preview && (
        <div className="card section-gap">
          <h3>Aperçu — {preview.columns.length} colonnes détectées</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>{preview.columns.map((c) => <th key={c}>{c}</th>)}</tr>
              </thead>
              <tbody>
                {preview.preview.map((row, i) => (
                  <tr key={i}>
                    {preview.columns.map((c) => <td key={c}>{String(row[c])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
