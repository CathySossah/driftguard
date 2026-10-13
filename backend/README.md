# DriftGuard — API Backend

API FastAPI implémentant le modèle de données et la logique métier décrits dans le
chapitre "Conception" du mémoire : authentification par rôle, monitoring, alertes
avec validation humaine, ré-entraînement (avec gestion d'échec et relance manuelle),
prédictions avec explicabilité SHAP.

## Installation

```bash
python -m venv venv
source venv/bin/activate  # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## Démarrage

```bash
uvicorn app.main:app --reload
```

L'API est disponible sur `http://localhost:8000`, avec la documentation interactive
auto-générée sur `http://localhost:8000/docs` (Swagger UI).

Par défaut, l'application utilise une base **SQLite** (`driftguard.db`, créée
automatiquement au premier démarrage) — idéal pour développer et tester sans
installer PostgreSQL. Pour la production, définissez la variable d'environnement :

```bash
export DATABASE_URL="postgresql://user:password@host:5432/driftguard"
export SECRET_KEY="une-cle-secrete-longue-et-aleatoire"
```

## Tester le flux complet

Deux scripts de test reproduisent des scénarios réels sans avoir besoin de lancer
un serveur séparé (utilisent `TestClient`, directement en mémoire) :

```bash
python test_flow.py                  # inscription, rôles, alerte -> ré-entraînement réel -> échec -> relance
python test_scenario.py              # scénario de dérive progressive avec calcul RÉEL via Evidently AI
python test_retraining.py            # pipeline complet : alerte -> entraînement réel -> publication MLflow vérifiée
python test_upload.py                # import réel d'un CSV, aperçu, rejets, contrôle d'accès
python test_real_dataset_pipeline.py # pipeline COMPLET sur un vrai CSV : import -> config -> entraînement -> monitoring -> alerte -> ré-entraînement
```

`test_real_dataset_pipeline.py` est le test le plus représentatif de ce que tu feras en
vrai : il génère un CSV à la structure proche d'IEEE-CIS Fraud Detection (mêmes noms de
colonnes clés : `TransactionDT`, `TransactionAmt`, `isFraud`...), l'importe via l'API comme
le ferait le bouton de la maquette, entraîne un premier modèle dessus, calcule une vraie
dérive par test statistique, et vérifie qu'une alerte se déclenche puis qu'un ré-entraînement
réel s'exécute — le tout sur des données réelles, pas simulées.

## Import de datasets réels (implémenté)

Un vrai bouton d'import existe côté frontend (page "Datasets"), branché sur :

- `POST /datasets/upload` (admin uniquement) : reçoit un fichier `.csv` en `multipart/form-data`
  avec un nom et un domaine (finance/santé/agriculture), le stocke dans `./data/uploads/`
  (configurable via `DATASET_UPLOAD_DIR`), valide qu'il est lisible par pandas et non vide,
  puis crée l'enregistrement `Dataset` correspondant. Tente de deviner automatiquement la
  colonne cible (`isFraud`, `target`, `label`, `readmitted`...) ; sinon, à préciser ensuite.
- `PATCH /datasets/{id}/configure` : désigne explicitement la colonne cible (obligatoire pour
  entraîner) et, en option, une colonne temporelle (pour un split référence/courant chronologique
  fidèle — sinon l'ordre des lignes du fichier est utilisé tel quel).
- `GET /datasets/{id}/preview` : renvoie les colonnes détectées et un extrait des premières
  lignes, pour vérifier visuellement l'import et choisir les bonnes colonnes.
- `POST /models/train-initial/{dataset_id}` : entraîne le tout premier modèle sur un dataset
  fraîchement configuré (aucun modèle n'existe encore pour lui) — nécessaire puisque le
  ré-entraînement classique (`alerts.py`) suppose qu'un modèle existe déjà.

Une fois un dataset configuré et un premier modèle entraîné, **le monitoring de dérive ET
les ré-entraînements suivants utilisent automatiquement ce vrai dataset** (voir
`services/monitoring_service.py` et `services/real_data_service.py`) : split référence/courant
(chronologique si une colonne temporelle est configurée, sinon par ordre des lignes), calcul
de dérive par variable en excluant la cible, la colonne temporelle elle-même, et les colonnes
de type identifiant (ex. `TransactionID` — leur "dérive" ne serait pas informative).

⚠️ **Limites assumées, documentées dans le code** :
- Le nombre de lignes utilisées pour l'entraînement est plafonné (`MAX_TRAINING_ROWS` dans
  `training_service.py`, 8000 par défaut) pour garder un temps d'exécution raisonnable en
  démonstration — à ajuster ou retirer pour un usage en production avec plus de ressources.
- Les colonnes catégorielles à trop forte cardinalité (ex. adresses e-mail complètes) sont
  écartées de l'entraînement plutôt qu'encodées, pour éviter une explosion du nombre de
  variables (`MAX_CATEGORY_CARDINALITY`).

⚠️ **Note technique importante** : un conflit de dépendances existait entre `evidently`
(qui a besoin du paquet `multipart`) et le système d'upload de fichiers de FastAPI (qui a
besoin de `python-multipart`) — les deux se marchaient dessus avec les anciennes versions de
FastAPI/Starlette. **Mettre à jour FastAPI vers la 0.141.1+ (Starlette 1.6+)** résout ce conflit
proprement ; c'est fait dans ce `requirements.txt`. Si tu repars d'un ancien environnement,
supprime le `venv` et réinstalle entièrement plutôt que de faire un `pip install -U` partiel.

### Datasets réels recommandés pour ton mémoire

- **Finance (principal)** : [IEEE-CIS Fraud Detection](https://www.kaggle.com/c/ieee-fraud-detection/data)
  (Kaggle, compte requis) — drift réel documenté via `TransactionDT`. Colonne cible : `isFraud`,
  colonne temporelle : `TransactionDT`.
- **Santé (généralisabilité)** : [Diabetes 130-US hospitals for years 1999-2008](https://archive.ics.uci.edu/dataset/296/diabetes+130-us+hospitals+for+years+1999-2008)
  (UCI Machine Learning Repository, téléchargement direct, pas de compte requis) — 10 ans de
  données réelles issues de 130 hôpitaux américains. Colonne cible : `readmitted`.
- **Agriculture (généralisabilité)** : [FAOSTAT — statistiques de rendement agricole](https://www.fao.org/faostat/en/#data/QCL)
  (FAO, téléchargement direct, filtrable par pays — tu peux cibler le Sénégal/l'Afrique de
  l'Ouest) — plusieurs décennies de données réelles, drift saisonnier/interannuel.

Une fois téléchargés, importe-les via le bouton "Importer un dataset" de la page Datasets,
configure la colonne cible (et temporelle si disponible), puis clique "Entraîner un modèle" —
inutile de toucher au serveur ou d'écrire du code.

## Monitoring réel avec Evidently AI (implémenté)

Contrairement à une version précédente qui acceptait un score de dérive fourni
manuellement, le monitoring est maintenant **calculé réellement** :

- `app/services/drift_service.py` : calcule le score de dérive avec Evidently AI
  (`DataDriftPreset`), en comparant un jeu de référence à un lot courant —
  test de Kolmogorov-Smirnov pour les variables continues, Z-test/Chi² pour
  les variables catégorielles (cf. chapitre 1 du mémoire).
- `app/services/data_simulator.py` : génère les données de référence et des
  lots "courants" avec un niveau de dérive contrôlable — permet de rejouer
  les scénarios expérimentaux (dérive progressive, brutale) du chapitre 2.4
  **sans dépendre du vrai dataset IEEE-CIS**. À remplacer par la lecture des
  transactions réelles en production.
- `app/services/scheduler.py` : planificateur APScheduler qui exécute
  automatiquement un cycle de monitoring toutes les 10 minutes (configurable)
  pour chaque modèle en production — démarré/arrêté avec le cycle de vie de
  l'application (`main.py`).
- `POST /monitoring/run-now/{model_version_id}` : déclenche un cycle immédiat
  (pratique pour la démo — pas besoin d'attendre le planificateur).
- `POST /monitoring/reset-scenario/{model_version_id}` : réinitialise le niveau
  de dérive simulé pour rejouer un scénario depuis le début.

## Structure du projet

```
app/
├── main.py           # Point d'entrée FastAPI, montage des routers, CORS
├── database.py       # Connexion SQLAlchemy (SQLite par défaut)
├── models.py         # Modèles ORM (User, Dataset, ModelVersion, MonitoringRun,
│                     #   Alert, RetrainingJob, PredictionLog)
├── schemas.py        # Schémas Pydantic (validation entrée/sortie API)
├── security.py       # Hachage bcrypt + tokens JWT
├── deps.py           # Dépendances FastAPI (utilisateur courant, rôle admin)
└── routers/
    ├── auth.py            # POST /auth/register, /auth/login
    ├── users.py           # Gestion des utilisateurs (admin)
    ├── datasets.py        # Liste des datasets (finance/santé/agriculture)
    ├── model_versions.py  # Versions de modèles, comparaison, déploiement
    ├── monitoring.py      # Enregistrement des runs + création auto d'alerte
    ├── alerts.py          # Validation/rejet des alertes (déclenche le ré-entraînement)
    ├── retraining.py      # Suivi des jobs, relance manuelle après échec
    └── predictions.py     # Prédictions utilisateur + historique
```

## Ré-entraînement réel avec publication MLflow (implémenté)

Autre placeholder désormais fonctionnel : la validation d'une alerte ne se contente
plus de créer un `RetrainingJob` en base, elle **entraîne réellement un nouveau
modèle et le journalise dans MLflow** :

- `app/services/training_service.py` : entraîne un `RandomForestClassifier` sur un
  jeu de données simulé (cf. limite ci-dessous), calcule ses métriques
  (accuracy, F1, rappel, précision), et journalise paramètres/métriques/artefact
  du modèle dans MLflow (`mlflow.sklearn.log_model`). Échoue proprement (avec un
  message d'erreur exploitable) si le jeu d'entraînement contient trop peu de cas
  positifs — situation réaliste, pas un échec artificiel.
- `app/services/retraining_service.py` : orchestre le job — appelle l'entraînement,
  puis en cas de succès crée une nouvelle `ModelVersion` (liée au run MLflow réel),
  archive l'ancienne version, et met à jour le `RetrainingJob` ; en cas d'échec,
  enregistre le message d'erreur (visible dans la maquette avec bouton "Relancer").
- Exécution en **tâche de fond** (`FastAPI BackgroundTasks`) déclenchée depuis
  `alerts.py` (validation d'alerte) et `retraining.py` (relance manuelle) : l'API
  répond immédiatement sans bloquer sur la durée de l'entraînement — alternative
  légère à Celery, suffisante pour ce volume ; à migrer vers Celery/RQ si la charge
  de ré-entraînement augmente en production.
- Tracking MLflow en local via SQLite (`sqlite:///./mlflow.db`, créé automatiquement)
  — remplacez `MLFLOW_TRACKING_URI` par l'URL de ton instance MLflow hébergée (ex.
  `https://mlflow-diabete.onrender.com`) pour t'y connecter en production.

⚠️ **Limite assumée** : faute d'accès au vrai dataset IEEE-CIS dans cet
environnement, `training_service.py` s'entraîne sur des données simulées
(`_build_training_frame()`, clairement isolée). La logique d'entraînement,
d'évaluation et de journalisation MLflow, elle, est entièrement réelle — il
suffira de remplacer cette seule fonction par le chargement du vrai dataset
pour rendre le pipeline pleinement opérationnel.

## Journal d'audit (implémenté) et correctif de la relance manuelle

- `GET /audit-logs/` (admin) : historique chronologique des actions — création
  de compte, désactivation, import de dataset, entraînement initial, validation
  ou rejet d'alerte, relance de ré-entraînement, déploiement manuel de version.
  Chaque entrée précise qui a fait l'action et sur quelle cible. Voir
  `services/audit_service.py` (fonction `log_action`, appelée depuis les
  routers concernés) et le modèle `AuditLog` dans `models.py`.
- **Bug corrigé** : relancer un entraînement initial en échec (bouton
  "Relancer manuellement" sur un job né du bouton "Entraîner un modèle" de la
  page Datasets, donc sans alerte associée) tombait à tort sur le message
  "Impossible de déterminer le modèle à ré-entraîner (alerte associée
  introuvable)". `RetrainingJob` a maintenant aussi un `dataset_id` (en plus
  de `alert_id`), et `POST /retraining-jobs/{id}/retry` choisit le bon chemin
  d'exécution selon lequel des deux est renseigné. Test de non-régression :
  `test_retry_and_audit.py`, qui reproduit exactement ce scénario.

## Prédictions réelles (implémenté)

`POST /predictions/` charge le modèle entraîné depuis MLflow et calcule une VRAIE
prédiction, avec une probabilité et une explication des variables les plus influentes.

- À l'entraînement (`training_service.py`), un « bundle » (modèle + métadonnées de
  préparation des variables) est journalisé dans MLflow (`model_bundle.joblib`).
- `GET /predictions/models` liste les modèles utilisables ; `GET /predictions/schema/{id}`
  décrit les champs du formulaire (les 12 variables les plus importantes du modèle ; les
  autres prennent une valeur typique du jeu d'entraînement).
- `services/ml_features.py` contient la préparation des variables, partagée entre
  l'entraînement et l'inférence (testée par `test_ml_features.py`, sans serveur).
- Explication : **par perturbation** (chaque variable est remplacée par une valeur typique
  et on mesure la variation de probabilité) — ce n'est pas un calcul de valeurs SHAP
  exactes ; à documenter comme tel dans le mémoire, ou à remplacer par la bibliothèque `shap`.
- Un modèle dont les fichiers MLflow ont disparu (ex. disque effacé au redémarrage) renvoie
  une erreur 409 explicite : il suffit de le ré-entraîner.

## Entraînement tolérant (aucun dataset refusé pour sa taille)

L'entraînement ne s'arrête plus pour « données insuffisantes ». Il s'adapte :
- très peu de lignes ou classe minoritaire rarissime : entraînement quand même, avec séparation
  adaptée (ou évaluation sur les données d'entraînement si moins de 8 lignes) ;
- une seule classe : le modèle prédit toujours cette classe ;
- cible continue (ex. rendement) : découpée en classes par quantiles (faible / moyen / élevé) ;
- cible texte très variée : les 19 valeurs les plus fréquentes sont gardées, le reste regroupé ;
- valeurs manquantes imputées, identifiants et textes libres écartés (mode de secours si rien ne reste).

Les adaptations sont consignées dans le paramètre MLflow `notes`. Seuls échecs possibles : aucune
colonne cible identifiable, aucune ligne avec cible renseignée, ou aucune variable explicative.
**Avec très peu de données, les métriques sont peu fiables** : à signaler dans le mémoire.

## Hébergement à faible mémoire (512 Mo)

- Le modèle de démonstration est **pré-entraîné à la construction de l'image Docker**
  (`python -m app.demo_model`, sans MLflow) et simplement enregistré en base au démarrage
  (`SEED_DEMO=true`) : plus d'entraînement au démarrage, donc plus de redémarrages en boucle.
- `LOW_MEMORY=true` désactive le monitoring automatique (le bouton « lancer maintenant » reste
  disponible) ; MLflow et Evidently ne sont chargés qu'au premier entraînement / calcul de dérive.
- Entraîner un modèle ou calculer la dérive reste gourmand : sur 512 Mo, cela peut encore
  dépasser la limite. Un plan à 2 Go lève ce risque.

## Sécurité et démarrage automatique

- **Code d'invitation admin** : si `ADMIN_SIGNUP_CODE` est défini, créer un compte
  administrateur exige ce code (champ ajouté sur la page d'inscription). Sans cette
  variable, la création reste libre (développement local uniquement).
- **Démarrage automatique** (`app/bootstrap.py`) : `ADMIN_EMAIL` + `ADMIN_PASSWORD` créent
  le compte admin, `DEMO_USER_EMAIL` + `DEMO_USER_PASSWORD` un compte utilisateur, et
  `SEED_DEMO=true` crée un dataset de démonstration et entraîne un premier modèle en
  arrière-plan. Utile quand la base est réinitialisée à chaque redémarrage.
- Voir `.env.example` pour la liste complète des variables.

```bash
python test_ml_features.py   # préparation + inférence (rapide, sans serveur)
python test_predictions.py   # code admin + démarrage auto + prédictions réelles (~1-2 min)
```

## Points à compléter avant mise en production

Ce backend pose une fondation fonctionnelle et testée, mais certains éléments
sont volontairement laissés en placeholder (marqués `TODO` dans le code) car ils
dépendent de choix d'infrastructure propres à ton déploiement :

- **Envoi d'e-mail** (`services/monitoring_service.py`) : à connecter à un service
  SMTP réel (ex. `smtplib`, ou un service comme SendGrid/Mailgun).
- **Seuils de dérive configurables par variable** (`services/monitoring_service.py`) :
  actuellement un seuil global unique ; la page "Paramètres" de la maquette prévoit
  un seuil par variable, à faire correspondre à une table de configuration.
- **File de tâches dédiée (Celery/RQ)** : `BackgroundTasks` suffit pour ce volume,
  mais n'offre pas de reprise sur erreur serveur ni de suivi de progression fin ;
  à migrer si le nombre de ré-entraînements simultanés augmente.
- **Migrations de base de données** : passer à Alembic dès que le schéma commence
  à évoluer, plutôt que `Base.metadata.create_all()`.
