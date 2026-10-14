// Cycle de vie d'une version de modèle (mêmes valeurs que ModelStatusEnum côté backend).
export const MODEL_STATUSES = [
  {
    key: 'en_test',
    label: 'En test',
    badge: 'pending',
    help: 'Modèle fraîchement entraîné, en cours d\'évaluation.',
  },
  {
    key: 'staging',
    label: 'Staging',
    badge: 'warn',
    help: 'Validé en pré-production, prêt à être promu. Il n\'est ni servi aux utilisateurs ni surveillé automatiquement.',
  },
  {
    key: 'en_production',
    label: 'En production',
    badge: 'ok',
    help: 'Servi aux utilisateurs pour les prédictions et surveillé (un seul par dataset).',
  },
  {
    key: 'archive',
    label: 'Archivé',
    badge: 'pending',
    help: 'Ancienne version retirée, conservée pour l\'historique et la comparaison.',
  },
]

export const statusInfo = (key) =>
  MODEL_STATUSES.find((s) => s.key === key) || { key, label: key, badge: 'pending', help: '' }
