import { useEffect, useState, useCallback, useRef } from 'react'
import api from '../api/client'
import { errorMessage } from '../utils/prediction'
import { statusInfo } from '../utils/modelStatus'

const domainLabels = {
  finance: 'Finance',
  sante: 'Santé',
  agriculture: 'Agriculture',
}

// Mêmes identifiants que le backend (app/services/ml_features.py : ALGORITHMS / BALANCING_METHODS)
const ALGORITHMS = [
  { key: 'random_forest', label: 'Random Forest' },
  { key: 'logistic_regression', label: 'Régression logistique' },
  { key: 'gradient_boosting', label: 'Gradient Boosting' },
]
const BALANCING = [
  { key: 'none', label: 'Aucun équilibrage', hint: 'Données et poids inchangés : sert de référence pour mesurer l\'effet des autres méthodes.' },
  { key: 'class_weight', label: 'Pondération des classes', hint: 'Les classes rares pèsent plus dans l\'apprentissage ; les données ne changent pas.' },
  { key: 'oversampling', label: 'Sur-échantillonnage', hint: 'Les exemples de la classe rare sont dupliqués jusqu\'à égaler la classe majoritaire.' },
  { key: 'undersampling', label: 'Sous-échantillonnage', hint: 'La classe majoritaire est réduite pour égaler la classe rare.' },
]
const algoLabel = (key) => ALGORITHMS.find((a) => a.key === key)?.label || key
const balancingLabel = (key) => BALANCING.find((b) => b.key === key)?.label || key
const pct = (v) => (v == null ? '—' : `${(v * 100).toFixed(1)} %`)
const fmtCsv = (v) => (v == null ? '' : String(v).replace('.', ','))

// Export du tableau de résultats (et des matrices de confusion) au format CSV, lisible dans Excel (français).
function exportResultsCsv(dataset, job) {
  const results = job.training_results || {}
  const config = results.config || {}
  const rows = (results.results || []).filter((r) => r.metrics)
  const lines = [
    `Dataset;${dataset.name}`,
    `Équilibrage;${balancingLabel(config.balancing || results.balancing)}`,
    `Évaluation;${results.evaluation || ''}`,
    '',
    'Algorithme;Accuracy;Précision;Rappel;F1-score;AUC;Durée (s);Meilleur',
    ...rows.map((r) => [
      r.label || algoLabel(r.algorithm), fmtCsv(r.metrics.accuracy), fmtCsv(r.metrics.precision),
      fmtCsv(r.metrics.recall), fmtCsv(r.metrics.f1), fmtCsv(r.metrics.roc_auc), fmtCsv(r.seconds), r.best ? 'oui' : '',
    ].join(';')),
  ]
  for (const r of rows) {
    if (!r.confusion_matrix) continue
    const { labels, matrix } = r.confusion_matrix
    lines.push('', `Matrice de confusion — ${r.label || algoLabel(r.algorithm)} (lignes : réel, colonnes : prédit)`)
    lines.push(['', ...labels].join(';'))
    matrix.forEach((row, i) => lines.push([labels[i], ...row].join(';')))
  }
  const blob = new Blob(['\uFEFF' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `resultats_${(dataset.name || 'entrainement').replace(/[^a-z0-9]+/gi, '_')}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

function ConfusionMatrix({ data, title }) {
  const { labels, matrix } = data
  return (
    <div style={{ marginTop: '1rem' }}>
      <h3 style={{ marginBottom: 6 }}>Matrice de confusion — {title}</h3>
      <p className="muted" style={{ fontSize: 11.5, marginBottom: 8 }}>Lignes : classe réelle · Colonnes : classe prédite</p>
      <div className="table-wrap">
        <table style={{ width: 'auto' }}>
          <thead>
            <tr><th></th>{labels.map((l) => <th key={l}>Prédit : {l}</th>)}</tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => {
              const total = row.reduce((a, b) => a + b, 0) || 1
              return (
                <tr key={labels[i]}>
                  <th>Réel : {labels[i]}</th>
                  {row.map((n, j) => (
                    <td
                      key={labels[j]}
                      style={{
                        textAlign: 'center',
                        fontWeight: i === j ? 700 : 400,
                        background: `rgba(201, 150, 43, ${(n / total) * (i === j ? 0.45 : 0.25)})`,
                      }}
                    >
                      {n}
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const statusBadge = { en_cours: ['warn', 'En cours'], reussi: ['ok', 'Terminé'], echoue: ['danger', 'Échec'] }

function TrainingPanel({ dataset, job, onRetry, onClose }) {
  const results = job.training_results || {}
  const config = results.config || {}
  const rows = results.results || []
  const [badgeCls, badgeText] = statusBadge[job.status] || ['pending', job.status]
  const percent = job.status === 'reussi' ? 100 : (job.progress || 0)
  const fillCls = job.status === 'reussi' ? 'done' : job.status === 'echoue' ? 'failed' : ''
  const [matrixOf, setMatrixOf] = useState(null) // algorithme dont on affiche la matrice de confusion
  const matrixRow = rows.find((r) => r.algorithm === matrixOf && r.confusion_matrix)

  return (
    <div className="card section-gap">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0 }}>Entraînement — {dataset.name}</h3>
        <div>
          <span className={`badge ${badgeCls}`}>{badgeText}</span>
          <button className="btn-sm" style={{ marginLeft: 10 }} onClick={onClose}>Fermer</button>
        </div>
      </div>

      <div style={{ margin: '1rem 0 0.4rem', display: 'flex', justifyContent: 'space-between', fontSize: 12.5 }}>
        <span>{job.progress_label || '—'}</span>
        <strong>{percent} %</strong>
      </div>
      <div className="progress-track">
        <div className={`progress-fill ${fillCls}`} style={{ width: `${percent}%` }} />
      </div>

      {(config.algorithms || config.balancing) && (
        <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
          Algorithmes : {(config.algorithms || results.algorithms || []).map(algoLabel).join(', ')}
          {' · '}Équilibrage : {balancingLabel(config.balancing || results.balancing)}
          {results.evaluation && <> {' · '}Évaluation : {results.evaluation}</>}
        </p>
      )}

      {results.published && (
        <p style={{ fontSize: 12.5, marginTop: 10 }}>
          Nouvelle version : <strong>v{results.published.version_number}</strong>{' '}
          <span className={`badge ${statusInfo(results.published.status).badge}`}>{statusInfo(results.published.status).label}</span>
          {results.published.status === 'staging' && (
            <span className="muted"> — à promouvoir en production depuis la page Modèles.</span>
          )}
        </p>
      )}

      {job.status === 'echoue' && (
        <div className="auth-error" style={{ marginTop: 12 }}>
          {job.error_message || 'L\'entraînement a échoué.'}
          <div style={{ marginTop: 8 }}>
            <button className="btn-sm" onClick={() => onRetry(job)}>Relancer avec les mêmes choix</button>
          </div>
        </div>
      )}

      {rows.length > 0 && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1.25rem' }}>
            <h3 style={{ margin: 0 }}>Résultats par algorithme</h3>
            <button className="btn-sm" onClick={() => exportResultsCsv(dataset, job)}>Exporter (CSV)</button>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Algorithme</th><th>Accuracy</th><th>Précision</th><th>Rappel</th><th>F1-score</th><th>AUC</th><th>Durée</th><th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  r.metrics ? (
                    <tr key={r.algorithm} className={r.best ? 'best-row' : ''}>
                      <td>{r.label || algoLabel(r.algorithm)} {r.best && <span className="badge ok">Meilleur — retenu</span>}</td>
                      <td>{pct(r.metrics.accuracy)}</td>
                      <td>{pct(r.metrics.precision)}</td>
                      <td>{pct(r.metrics.recall)}</td>
                      <td>{pct(r.metrics.f1)}</td>
                      <td>{r.metrics.roc_auc == null ? '—' : r.metrics.roc_auc.toFixed(3)}</td>
                      <td>{r.seconds} s</td>
                      <td>
                        {r.confusion_matrix && (
                          <button className="btn-sm" onClick={() => setMatrixOf(matrixOf === r.algorithm ? null : r.algorithm)}>
                            {matrixOf === r.algorithm ? 'Masquer la matrice' : 'Matrice de confusion'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ) : (
                    <tr key={r.algorithm}>
                      <td>{r.label || algoLabel(r.algorithm)}</td>
                      <td colSpan={7}><span className="badge danger">Échec</span> {r.error}</td>
                    </tr>
                  )
                ))}
              </tbody>
            </table>
          </div>
          {matrixRow && <ConfusionMatrix data={matrixRow.confusion_matrix} title={matrixRow.label || algoLabel(matrixRow.algorithm)} />}
          <p className="muted" style={{ fontSize: 11.5, marginTop: 8 }}>
            Le meilleur algorithme est celui qui obtient le F1-score le plus élevé sur le jeu de test ;
            c'est lui qui devient la nouvelle version du modèle.
          </p>
        </>
      )}

      {(results.notes || []).length > 0 && (
        <ul className="muted" style={{ fontSize: 12, marginTop: 8, paddingLeft: 18 }}>
          {results.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
    </div>
  )
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
  const [trainPanel, setTrainPanel] = useState(null) // dataset dont on choisit les options d'entraînement
  const [selAlgos, setSelAlgos] = useState(['random_forest'])
  const [balancing, setBalancing] = useState('class_weight')
  const [targetStatus, setTargetStatus] = useState('') // '' = automatique
  const [jobsByDataset, setJobsByDataset] = useState({}) // dernier entraînement de chaque dataset
  const [progressFor, setProgressFor] = useState(null) // dataset dont on affiche la progression / les résultats

  const [file, setFile] = useState(null)
  const [name, setName] = useState('')
  const [domain, setDomain] = useState('finance')
  const fileInputRef = useRef(null)

  const loadJobs = useCallback(async () => {
    try {
      const { data } = await api.get('/retraining-jobs/')
      const latest = {}
      for (const job of data) {
        // la liste est triée du plus récent au plus ancien : on garde le premier de chaque dataset
        if (job.dataset_id && !latest[job.dataset_id]) latest[job.dataset_id] = job
      }
      setJobsByDataset(latest)
    } catch {
      /* l'onglet reste utilisable sans l'historique */
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    const { data } = await api.get('/datasets/')
    setDatasets(data)
    setLoading(false)
    loadJobs()
  }, [loadJobs])

  useEffect(() => { load() }, [load])

  // Tant qu'un entraînement est en cours, on interroge le serveur toutes les 2 secondes
  // pour mettre à jour le pourcentage d'avancement.
  const runningIds = Object.values(jobsByDataset).filter((j) => j.status === 'en_cours').map((j) => j.id)
  const runningKey = runningIds.join(',')
  useEffect(() => {
    if (!runningKey) return undefined
    const timer = setInterval(async () => {
      for (const id of runningKey.split(',')) {
        try {
          const { data } = await api.get(`/retraining-jobs/${id}`)
          if (data.dataset_id) setJobsByDataset((prev) => ({ ...prev, [data.dataset_id]: data }))
        } catch {
          /* on réessaiera au prochain tour */
        }
      }
    }, 2000)
    return () => clearInterval(timer)
  }, [runningKey])

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

  function openTrainPanel(dataset) {
    setError(null)
    setSuccess(null)
    setTrainPanel(dataset)
  }

  function toggleAlgo(key) {
    setSelAlgos((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]))
  }

  async function handleStartTraining(e) {
    e.preventDefault()
    if (selAlgos.length === 0) {
      setError('Choisis au moins un algorithme.')
      return
    }
    const datasetId = trainPanel.id
    setTrainingId(datasetId)
    setError(null)
    setSuccess(null)
    try {
      const { data: job } = await api.post(`/models/train-initial/${datasetId}`, {
        algorithms: selAlgos,
        balancing,
        target_status: targetStatus || null,
      })
      setJobsByDataset((prev) => ({ ...prev, [datasetId]: job }))
      setProgressFor(datasetId)
      setTrainPanel(null)
    } catch (err) {
      setError(errorMessage(err, 'Impossible de lancer l\'entraînement.'))
    } finally {
      setTrainingId(null)
    }
  }

  async function handleRetry(job) {
    setError(null)
    try {
      const { data: newJob } = await api.post(`/retraining-jobs/${job.id}/retry`)
      if (newJob.dataset_id) setJobsByDataset((prev) => ({ ...prev, [newJob.dataset_id]: newJob }))
    } catch (err) {
      setError(errorMessage(err, 'Impossible de relancer l\'entraînement.'))
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
                          disabled={jobsByDataset[d.id]?.status === 'en_cours'}
                          onClick={() => openTrainPanel(d)}
                        >
                          Entraîner un modèle
                        </button>
                      )}
                      {jobsByDataset[d.id] && (
                        <button className="btn-sm" onClick={() => setProgressFor(d.id)}>
                          {jobsByDataset[d.id].status === 'en_cours'
                            ? `Progression (${jobsByDataset[d.id].progress || 0} %)`
                            : 'Progression et résultats'}
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

      {trainPanel && (
        <div className="card section-gap">
          <h3>Entraîner un modèle — {trainPanel.name}</h3>
          <form onSubmit={handleStartTraining}>
            <div className="grid grid-2">
              <div>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
                  Algorithmes à entraîner et comparer
                </label>
                {ALGORITHMS.map((a) => (
                  <label className="check-row" key={a.key}>
                    <input type="checkbox" checked={selAlgos.includes(a.key)} onChange={() => toggleAlgo(a.key)} />
                    {a.label}
                  </label>
                ))}
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label>Méthode d'équilibrage des classes</label>
                <select value={balancing} onChange={(e) => setBalancing(e.target.value)}>
                  {BALANCING.map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}
                </select>
                <p className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
                  {BALANCING.find((b) => b.key === balancing)?.hint}
                </p>
              </div>
            </div>
            <div className="field section-gap" style={{ marginBottom: 0, maxWidth: 420 }}>
              <label>Statut de la nouvelle version</label>
              <select value={targetStatus} onChange={(e) => setTargetStatus(e.target.value)}>
                <option value="">Automatique (production s'il n'y a pas encore de modèle, sinon staging)</option>
                <option value="staging">Staging (à valider avant la production)</option>
                <option value="en_production">Directement en production</option>
              </select>
            </div>
            <button className="btn-gold section-gap" disabled={trainingId === trainPanel.id}>
              {trainingId === trainPanel.id ? 'Lancement...' : 'Lancer l\'entraînement'}
            </button>
            <button type="button" className="btn-sm" style={{ marginLeft: 10 }} onClick={() => setTrainPanel(null)}>
              Annuler
            </button>
          </form>
        </div>
      )}

      {progressFor && jobsByDataset[progressFor] && (
        <TrainingPanel
          dataset={datasets.find((d) => d.id === progressFor) || { name: '' }}
          job={jobsByDataset[progressFor]}
          onRetry={handleRetry}
          onClose={() => setProgressFor(null)}
        />
      )}

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
