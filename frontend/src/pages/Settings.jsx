export default function Settings() {
  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Paramètres</h1>
          <div className="subtitle">Configuration du monitoring et des seuils d'alerte</div>
        </div>
      </div>

      <div className="card" style={{ background: 'var(--gold-softer)', borderColor: 'var(--gold-soft)' }}>
        <p style={{ fontSize: 13 }}>
          <strong>Interface prête, backend à compléter :</strong> cette page reflète la maquette,
          mais le backend n'expose pas encore d'endpoint pour lire/écrire les seuils par variable.
          Actuellement, le seuil est une constante globale (<code>DEFAULT_DRIFT_THRESHOLD</code> dans{' '}
          <code>monitoring_service.py</code>). Prochaine étape : une table <code>settings</code> +
          des routes <code>GET/PATCH /settings</code>.
        </p>
      </div>

      <div className="card section-gap">
        <h3>Seuils de dérive par variable (aperçu, non connecté)</h3>
        {['purchase_hour', 'TransactionAmt', 'device_type', 'card_type'].map((name) => (
          <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 0', borderBottom: '1px solid #F1ECDF' }}>
            <span style={{ width: 150, fontSize: 13 }}>{name}</span>
            <input type="range" min="0" max="1" step="0.01" defaultValue="0.2" style={{ flex: 1, accentColor: 'var(--gold)' }} disabled />
            <span className="muted" style={{ width: 44, textAlign: 'right', fontSize: 12.5 }}>0.20</span>
          </div>
        ))}
      </div>
    </div>
  )
}
