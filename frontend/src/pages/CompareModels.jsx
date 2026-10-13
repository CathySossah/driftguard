import { useEffect, useState } from 'react'
import api from '../api/client'

export default function CompareModels() {
  const [versions, setVersions] = useState([])
  const [idA, setIdA] = useState('')
  const [idB, setIdB] = useState('')

  useEffect(() => {
    api.get('/models/').then(({ data }) => {
      const sorted = data.sort((a, b) => b.version_number - a.version_number)
      setVersions(sorted)
      if (sorted.length >= 2) {
        setIdA(sorted[1].id)
        setIdB(sorted[0].id)
      }
    })
  }, [])

  const versionA = versions.find((v) => v.id === idA)
  const versionB = versions.find((v) => v.id === idB)

  const rows = [
    { label: 'Précision', key: 'accuracy', format: (v) => v != null ? `${(v * 100).toFixed(1)}%` : '—' },
    { label: 'F1-score', key: 'f1', format: (v) => v ?? '—' },
    { label: 'Rappel', key: 'recall', format: (v) => v ?? '—' },
    { label: 'Précision (precision)', key: 'precision', format: (v) => v ?? '—' },
  ]

  return (
    <div>
      <div className="topbar">
        <div>
          <h1>Comparer les modèles</h1>
          <div className="subtitle">Comparaison côte à côte de deux versions avant validation d'un déploiement</div>
        </div>
      </div>

      {versions.length < 2 ? (
        <div className="card empty-state">
          <h3>Pas assez de versions</h3>
          <p>Il faut au moins deux versions de modèle pour pouvoir les comparer.</p>
        </div>
      ) : (
        <>
          <div className="card">
            <div className="grid grid-2">
              <div className="field" style={{ margin: 0 }}>
                <label>Version A</label>
                <select value={idA} onChange={(e) => setIdA(e.target.value)}>
                  {versions.map((v) => <option key={v.id} value={v.id}>v{v.version_number}</option>)}
                </select>
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label>Version B</label>
                <select value={idB} onChange={(e) => setIdB(e.target.value)}>
                  {versions.map((v) => <option key={v.id} value={v.id}>v{v.version_number}</option>)}
                </select>
              </div>
            </div>
          </div>

          <div className="card section-gap">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Métrique</th><th>v{versionA?.version_number} (A)</th><th>v{versionB?.version_number} (B)</th></tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.key}>
                      <td>{row.label}</td>
                      <td>{row.format(versionA?.metrics?.[row.key])}</td>
                      <td>{row.format(versionB?.metrics?.[row.key])}</td>
                    </tr>
                  ))}
                  <tr>
                    <td>Statut</td>
                    <td className="muted">{versionA?.status}</td>
                    <td className="muted">{versionB?.status}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
