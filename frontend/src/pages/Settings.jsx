import { useCallback, useEffect, useState } from 'react'
import api from '../api/client'
import { errorMessage } from '../utils/prediction'

const DEFAULTS = { alert_threshold: 0.2, pvalue_threshold: 0.05 }
const fmtNum = (v) => (v == null ? '—' : String(Math.round(v * 10000) / 10000))

export default function Settings() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [saved, setSaved] = useState({ ...DEFAULTS, variable_thresholds: {} })
  const [variables, setVariables] = useState([])
  const [alertPct, setAlertPct] = useState(20)
  const [pvalue, setPvalue] = useState('0.05')
  const [custom, setCustom] = useState({}) // nom de variable -> texte saisi ('' = seuil par défaut)
  const [emailEnabled, setEmailEnabled] = useState(true)
  const [emailProvider, setEmailProvider] = useState(null)
  const [testing, setTesting] = useState(false)

  const load = useCallback(async () => {
    try {
      const [{ data: s }, { data: v }] = await Promise.all([
        api.get('/settings/'),
        api.get('/settings/variables'),
      ])
      setSaved(s)
      setVariables(v)
      setAlertPct(Math.round(s.alert_threshold * 100))
      setPvalue(String(s.pvalue_threshold))
      setEmailEnabled(s.email_alerts_enabled !== false)
      setEmailProvider(s.email_provider)
      setCustom(Object.fromEntries(Object.entries(s.variable_thresholds).map(([k, val]) => [k, String(val)])))
    } catch (err) {
      setError(errorMessage(err, 'Impossible de charger les paramètres.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function save(payload, message) {
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      await api.patch('/settings/', payload)
      setSuccess(message)
      await load()
    } catch (err) {
      setError(errorMessage(err, 'L\'enregistrement a échoué.'))
    } finally {
      setSaving(false)
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    const names = new Set([...variables.map((v) => v.name), ...Object.keys(saved.variable_thresholds)])
    const variable_thresholds = {}
    for (const name of names) {
      const text = (custom[name] ?? '').trim()
      if (text !== '') variable_thresholds[name] = Number(text.replace(',', '.'))
      else if (name in saved.variable_thresholds) variable_thresholds[name] = null // retire le seuil personnalisé
    }
    save(
      {
        alert_threshold: alertPct / 100,
        pvalue_threshold: Number(String(pvalue).replace(',', '.')),
        variable_thresholds,
        email_alerts_enabled: emailEnabled,
      },
      'Paramètres enregistrés : ils s\'appliquent dès le prochain cycle de monitoring.',
    )
  }

  async function handleTestEmail() {
    setTesting(true)
    setError(null)
    setSuccess(null)
    try {
      const { data } = await api.post('/settings/test-email')
      setSuccess(data.message)
    } catch (err) {
      setError(errorMessage(err, 'L\'envoi de l\'e-mail de test a échoué.'))
    } finally {
      setTesting(false)
    }
  }

  function handleReset() {
    const variable_thresholds = Object.fromEntries(Object.keys(saved.variable_thresholds).map((k) => [k, null]))
    save(
      { ...DEFAULTS, variable_thresholds, email_alerts_enabled: true },
      'Valeurs par défaut rétablies.',
    )
  }

  if (loading) return <div className="page-loading"><span className="spinner" /> Chargement...</div>

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Paramètres</h1>
          <div className="subtitle">Seuils de détection du drift et d'alerte</div>
        </div>
      </div>

      {error && <div className="auth-error">{error}</div>}
      {success && <div className="auth-error" style={{ background: 'var(--success-bg)', color: 'var(--success)' }}>{success}</div>}

      <form onSubmit={handleSubmit}>
        <div className="card">
          <h3>Seuil d'alerte</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <input
              type="range" min="1" max="100" step="1" value={alertPct}
              onChange={(e) => setAlertPct(Number(e.target.value))}
              style={{ flex: 1, accentColor: 'var(--gold)' }}
            />
            <strong style={{ width: 56, textAlign: 'right' }}>{alertPct} %</strong>
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            Une alerte est créée lorsque la part de variables en dérive atteint ce seuil. Elle doit ensuite être
            validée par un administrateur avant tout ré-entraînement.
          </p>
        </div>

        <div className="card section-gap">
          <h3>Sensibilité du test statistique</h3>
          <div className="field" style={{ margin: 0, maxWidth: 260 }}>
            <label>Seuil de p-value (défaut : 0,05)</label>
            <input
              type="number" min="0.001" max="0.5" step="0.001" required
              value={pvalue} onChange={(e) => setPvalue(e.target.value)}
            />
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            Une variable est jugée en dérive si la p-value de son test (Kolmogorov-Smirnov, Z-test...) est inférieure
            à ce seuil. Plus la valeur est élevée, plus la détection est sensible.
          </p>
        </div>

        <div className="card section-gap">
          <h3>Seuils par variable</h3>
          {variables.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>
              Aucune variable observée pour l'instant. Lancez un cycle de monitoring depuis le tableau de bord :
              les variables du modèle apparaîtront ici et pourront recevoir leur propre seuil.
            </p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Variable</th><th>Test</th><th>Dernière valeur</th><th>Seuil par défaut</th>
                    <th>Seuil personnalisé</th><th>État</th>
                  </tr>
                </thead>
                <tbody>
                  {variables.map((v) => (
                    <tr key={v.name}>
                      <td>{v.name}</td>
                      <td>{v.kind === 'distance' ? 'Distance' : v.kind === 'p_value' ? 'p-value' : '—'}</td>
                      <td>{fmtNum(v.last_value)}</td>
                      <td>{fmtNum(v.default_threshold)}</td>
                      <td>
                        <input
                          type="number" min="0.001" max="1" step="0.001" style={{ width: 110 }}
                          placeholder={fmtNum(v.default_threshold)}
                          value={custom[v.name] ?? ''}
                          onChange={(e) => setCustom({ ...custom, [v.name]: e.target.value })}
                        />
                      </td>
                      <td>
                        {v.drifted == null
                          ? <span className="badge pending">—</span>
                          : v.drifted
                            ? <span className="badge danger">En dérive</span>
                            : <span className="badge ok">Stable</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
            Laissez vide pour utiliser le seuil par défaut. Pour un test à p-value, la variable dérive si la p-value est
            inférieure au seuil ; pour un test à distance (grands jeux de données), elle dérive si la distance atteint
            le seuil. Le seuil d'une variable remplace le seuil global de p-value.
          </p>
        </div>

        <div className="card section-gap">
          <h3>Alertes par e-mail</h3>
          <label className="check-row">
            <input type="checkbox" checked={emailEnabled} onChange={(e) => setEmailEnabled(e.target.checked)} />
            Prévenir les administrateurs par e-mail lorsqu'une alerte de drift est créée
          </label>
          <p style={{ fontSize: 12.5, marginTop: 6 }}>
            Service d'envoi :{' '}
            {emailProvider
              ? <span className="badge ok">Configuré ({{ resend: 'Resend', brevo: 'Brevo' }[emailProvider] || 'SMTP'})</span>
              : <span className="badge warn">Non configuré</span>}
          </p>
          {!emailProvider && (
            <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
              Aucun e-mail ne partira tant que le serveur n'a pas la variable <code>RESEND_API_KEY</code>{' '}
              (service gratuit resend.com). Les alertes restent visibles dans l'application.
            </p>
          )}
          {emailProvider === 'resend' && (
            <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
              Sans domaine vérifié chez Resend, les e-mails ne sont délivrés qu'à l'adresse du compte Resend
              (utilisez la même adresse que celle de l'administrateur).
            </p>
          )}
          <button type="button" className="btn-sm" style={{ marginTop: 10 }} disabled={testing || !emailProvider} onClick={handleTestEmail}>
            {testing ? 'Envoi...' : 'Envoyer un e-mail de test'}
          </button>
        </div>

        <div className="section-gap">
          <button className="btn-gold" disabled={saving}>{saving ? 'Enregistrement...' : 'Enregistrer les paramètres'}</button>
          <button type="button" className="btn-sm" style={{ marginLeft: 10 }} disabled={saving} onClick={handleReset}>
            Rétablir les valeurs par défaut
          </button>
        </div>
      </form>
    </div>
  )
}
