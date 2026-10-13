import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import { predictionDisplay } from '../utils/prediction'

export default function UserHistory() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/predictions/history')
      .then(({ data }) => setHistory(data))
      .catch(() => setHistory([]))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="page-loading"><span className="spinner" /> Chargement...</div>

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Historique</h1>
          <div className="subtitle">Vos dernières requêtes de prédiction</div>
        </div>
      </div>

      <div className="card">
        {history.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" style={{ margin: '0 auto 1rem', display: 'block' }}>
              <circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3.5 2" />
            </svg>
            <h3>Aucune prédiction pour le moment</h3>
            <p>Vos futures prédictions apparaîtront ici, avec leur résultat et leur date.</p>
            <button className="btn-gold" style={{ marginTop: '1.25rem' }} onClick={() => navigate('/predict')}>
              Faire une prédiction
            </button>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Résultat</th><th>Score</th></tr></thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id}>
                    <td>{new Date(h.created_at).toLocaleString('fr-FR')}</td>
                    <td>
                      <span className={`badge ${predictionDisplay(h.prediction).cls}`}>{predictionDisplay(h.prediction).badge}</span>
                    </td>
                    <td>{h.probability != null ? `${(h.probability * 100).toFixed(1)} %` : '—'}</td>
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
