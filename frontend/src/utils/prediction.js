// Affichage d'un résultat de prédiction : "legitime" / "suspecte" pour la
// détection de fraude, sinon le libellé de la classe prédite tel quel.
export function predictionDisplay(prediction) {
  if (prediction === 'legitime') return { title: 'Transaction légitime', badge: 'Légitime', cls: 'ok' }
  if (prediction === 'suspecte') return { title: 'Transaction suspecte', badge: 'Suspecte', cls: 'danger' }
  return { title: `Résultat : ${prediction}`, badge: String(prediction), cls: 'pending' }
}

// Extrait un message lisible d'une erreur axios (le détail peut être une
// chaîne, ou une liste pour les erreurs de validation).
export function errorMessage(err, fallback) {
  const detail = err?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}
