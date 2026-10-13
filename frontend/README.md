# DriftGuard — Frontend (React + PWA)

Interface web ET mobile (Progressive Web App) pour la plateforme DriftGuard,
connectée à l'API backend FastAPI.

## Installation

```bash
npm install
```

## Configuration

Par défaut, l'application appelle l'API sur `http://localhost:8000`. Pour changer
cette URL (ex. déploiement), copie `.env.example` en `.env` et adapte :

```bash
cp .env.example .env
```

## Démarrage (développement)

⚠️ Le **backend doit déjà tourner** (voir le README du dossier `backend/`,
`uvicorn app.main:app --reload`) avant de lancer le frontend.

```bash
npm run dev
```

Ouvre `http://localhost:5173`. Crée un premier compte administrateur via la page
"Créer un compte", puis connecte-toi.

## Build de production

```bash
npm run build
npm run preview   # pour tester le build localement
```

Le dossier `dist/` contient l'application prête à héberger (Netlify, Vercel,
Render, ou tout serveur statique).

## Web et mobile : comment ça marche

C'est une **Progressive Web App (PWA)** : une seule base de code React, qui
s'adapte automatiquement à la taille d'écran (sidebar sur desktop, barre de
navigation en bas sur mobile — voir `src/styles/theme.css`, section
"Responsive"). Sur téléphone, en ouvrant l'URL dans Chrome ou Safari, l'utilisateur
peut choisir "Ajouter à l'écran d'accueil" : l'application s'installe alors avec
sa propre icône et s'ouvre en plein écran, comme une application native.

La configuration PWA (icônes, couleurs, nom de l'app) est dans `vite.config.js`
(plugin `vite-plugin-pwa`). Les icônes se trouvent dans `public/icons/` —
ce sont des icônes provisoires simples, à remplacer par un vrai logo avant la
soutenance si tu veux un rendu plus soigné.

## Structure du projet

```
src/
├── api/client.js          # Client HTTP (axios) avec gestion automatique du JWT
├── context/AuthContext.jsx # État global d'authentification (connexion, rôle)
├── components/
│   ├── Layout.jsx          # Shell responsive (sidebar desktop / barre mobile)
│   ├── ProtectedRoute.jsx  # Protection des routes par rôle
│   └── icons.jsx           # Icônes SVG de la navigation
├── pages/
│   ├── Login.jsx, Signup.jsx
│   ├── Dashboard.jsx       # Tableau de bord admin (jauge, KPIs, historique — données réelles)
│   ├── Monitoring.jsx      # Détail par variable + historique des runs
│   ├── Alerts.jsx          # Validation/rejet réels (déclenche le ré-entraînement backend)
│   ├── Models.jsx          # Versions + historique de ré-entraînement + relance après échec
│   ├── CompareModels.jsx   # Comparaison de deux versions
│   ├── Users.jsx           # Gestion des utilisateurs (admin)
│   ├── Settings.jsx, Audit.jsx  # Interfaces prêtes, en attente des endpoints backend correspondants
│   └── UserHome.jsx, UserPredict.jsx, UserHistory.jsx  # Espace utilisateur
└── styles/theme.css        # Palette claire + règles responsive (sidebar <-> bottom nav)
```

## Ce qui est réellement connecté au backend

Toutes les pages listées ci-dessus font de vrais appels API (pas de données
simulées côté frontend) : authentification, dashboard, monitoring, alertes
(validation → déclenche un vrai ré-entraînement MLflow côté serveur), modèles,
comparaison, utilisateurs, prédictions avec explication SHAP, historique.

Seules **Settings** et **Audit** sont pour l'instant des interfaces "prêtes mais
non connectées", le backend n'exposant pas encore ces endpoints (voir le README
du backend, section "Points à compléter").
