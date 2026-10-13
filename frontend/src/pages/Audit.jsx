import { useEffect, useState } from 'react'
import api from '../api/client'

const actionLabels = {
  'user.created': 'Création de compte',
  'user.deactivated': 'Désactivation de compte',
  'alert.validated': "Validation d'alerte",
  'alert.rejected': "Rejet d'alerte",
  'retraining.retried': 'Relance de ré-entraînement',
  'model.initial_training': 'Entraînement initial déclenché',
  'model.deployed': 'Déploiement manuel de modèle',
  'dataset.uploaded': "Import de dataset",
}

export default function Audit() {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/audit-logs/')
      .then(({ data }) => setLogs(data))
      .catch(() => setError('Impossible de charger le journal d\'audit.'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Journal d'audit</h1>
          <div className="subtitle">Historique des actions effectuées sur la plateforme</div>
        </div>
      </div>

      {error && <div className="auth-error">{error}</div>}

      <div className="card">
        {loading ? (
          <div className="page-loading"><span className="spinner" /> Chargement...</div>
        ) : logs.length === 0 ? (
          <div className="empty-state">
            <h3>Aucune action journalisée</h3>
            <p>Les actions (validations d'alertes, imports, créations de compte...) apparaîtront ici au fur et à mesure.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Utilisateur</th><th>Action</th><th>Cible</th></tr></thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id}>
                    <td>{new Date(log.created_at).toLocaleString('fr-FR')}</td>
                    <td>{log.user_name || 'Inconnu'}</td>
                    <td>{actionLabels[log.action] || log.action}</td>
                    <td className="muted">{log.target || '—'}</td>
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
