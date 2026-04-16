# Projet Data Pipelines DSIA — E-Commerce Sénégal

**Membre du groupe** :
Mouhamadou Makhtar DIOUF — Master 2 DSIA, ISI Dakar   
Mamadou Moustapha Ndiaye

---

## Objectif du Projet

### Contexte

En tant que Data Engineer dans une marketplace e-commerce sénégalaise, la mission est de concevoir et déployer une **plateforme de data pipelines** capable de :

- **Ingérer des flux de données en temps réel** — transactions de paiement Wave/Orange Money
- **Orchestrer des traitements batch quotidiens** — mise à jour du catalogue produits
- **Détecter des anomalies en temps réel** — et les pousser sur un topic Kafka dédié
- **Exposer les données** pour qu'elles soient facilement exploitables (Marimo, Jupyter, MinIO)

### Les 3 sources de données identifiées

| # | Type | Source | Technologie |
|---|------|--------|-------------|
| 1 | **Temps réel** | Transactions Wave / Orange Money | Kafka Producer |
| 2 | **Batch** | Catalogue produits (CSV quotidien) | Airflow DAG |
| 3 | **Choix libre** | Taux de change XOF/USD (API simulée) | Kafka Producer + PostgreSQL |

---

## Process Suivi

### Phase 1 — Analyse et conception

1. Identification des sources de données métier (paiements, catalogue, taux de change)
2. Définition des règles d'anomalie (seuils de montant, pays autorisés, statuts d'échec)
3. Conception du schéma PostgreSQL : 5 tables + 2 vues analytiques
4. Choix de l'architecture (Lambda Architecture simplifiée : batch + streaming)

### Phase 2 — Infrastructure Docker

1. Rédaction du `docker-compose.yml` : 8 services orchestrés
2. Création du schéma SQL (`sql/schema.sql`)
3. Configuration des variables d'environnement (`.env`)
4. Ajout de la connexion `postgres_default` dans Airflow au démarrage

### Phase 3 — Pipelines

#### Pipeline temps réel (Kafka)

```
paiement_producer.py ──► topic: paiements-senegal
                                   │
                         anomaly_consumer.py
                          ├─► PostgreSQL (table paiements)
                          ├─► PostgreSQL (table anomalies) ← si anomalie
                          └─► topic: anomalies-paiements  ← topic dédié (énoncé)
```

#### Pipeline taux de change (Source 3)

```
exchange_rate_producer.py ──► topic: taux-change
                                        │
                              exchange_rate_consumer.py
                                        │
                               PostgreSQL (table taux_change)
                                        │
                               DAG Airflow (tâche 2 : obtenir_taux_change)
```

#### Pipeline batch (Airflow DAG — 6 tâches)

```
[1] lire_catalogue (CSV)
        │
[2] obtenir_taux_change (PostgreSQL)
        │
[3] calculer_prix_usd
        │
[4] inserer_produits (PostgreSQL UPSERT)
        │
[5] generer_stats (table stats_quotidiennes)
        │
[6] exporter_minio (MinIO data lake)
```

### Phase 4 — Tests et validation

1. Test de bout en bout : producer → consumer → PostgreSQL → anomalies
2. Exécution manuelle du DAG Airflow (Trigger depuis l'UI)
3. Vérification des exports MinIO via la console (port 9001)
4. Consultation des données via Marimo (port 2718) et Jupyter (port 8888)

### Phase 5 — Documentation

1. README.md (ce document)
2. Docstrings dans chaque script Python
3. Commentaires dans le DAG Airflow et le `docker-compose.yml`

---

## Stack Technique

### Services Docker

| Service | Image | Port(s) | Rôle |
|---|---|---|---|
| **Kafka** (KRaft) | `confluentinc/cp-kafka:7.6.0` | 9092 | Broker streaming — mode KRaft (sans Zookeeper) |
| **Kafbat UI** | `ghcr.io/kafbat/kafka-ui` | 8090 | Monitoring des topics Kafka |
| **PostgreSQL** | `postgres:15-alpine` | 5432 | Base de données OLTP |
| **MinIO** | `minio/minio:latest` | 9000, 9001 | Data lake (rapports batch, snapshots) |
| **Airflow Webserver** | `apache/airflow:2.7.3-python3.11` | 8080 | Orchestration + interface web |
| **Airflow Scheduler** | `apache/airflow:2.7.3-python3.11` | — | Exécution des DAGs |
| **Marimo** | Custom (python:3.11-slim) | 2718 | Dashboard réactif — exposition données |
| **Jupyter** | `jupyter/datascience-notebook` | 8888 | Notebooks d'analyse |

### Topics Kafka

| Topic | Producteur | Consommateur | Usage |
|---|---|---|---|
| `paiements-senegal` | `paiement_producer.py` | `anomaly_consumer.py` | Flux paiements temps réel |
| **`anomalies-paiements`** | `anomaly_consumer.py` | — | **Topic dédié anomalies** |
| `taux-change` | `exchange_rate_producer.py` | `exchange_rate_consumer.py` | Taux de change XOF/USD → PostgreSQL |

### Schéma PostgreSQL

| Table | Description |
|---|---|
| `paiements` | Transactions Wave/Orange Money insérées par le consumer |
| `anomalies` | Anomalies détectées en temps réel |
| `produits` | Catalogue enrichi (prix XOF + prix USD) mis à jour par Airflow |
| `taux_change` | Historique taux XOF/USD |
| `stats_quotidiennes` | Agrégats journaliers générés par le DAG |

### Langages et bibliothèques

- **Python 3.11** : `confluent-kafka`, `psycopg2-binary`, `pandas`, `minio`, `faker`, `marimo`
- **SQL** : PostgreSQL 15 avec vues analytiques (`v_transactions_jour`, `v_anomalies_actives`)

---

## Instructions de Déploiement
### . Installer les dépendances Python (local)

```bash
pip install -r requirements.txt
```

### . Démarrer la stack Docker

```bash
docker-compose up -d
```

Vérifier que tous les services sont `Up` (2-3 minutes) :

```bash
docker-compose ps
```

### . Vérifier les services

| Service | URL | Identifiants |
|---|---|---|
| Airflow | http://localhost:8080 | admin / admin |
| Kafbat UI | http://localhost:8090 | — |
| Marimo | http://localhost:2718 | — |
| Jupyter | http://localhost:8888 | — |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |

```bash
# Vérifier les tables PostgreSQL
docker exec -it postgres psql -U dataeng -d ecommerce_senegal -c "\dt"
```

### . Initialiser les données de test

```bash
python scripts/generate_sample_data.py
# Résultat : 200 paiements + 30 jours de taux de change
```

### . Lancer les pipelines temps réel

```bash
# Terminal 1 — Source 3 producer : taux de change → topic taux-change
python kafka/producers/exchange_rate_producer.py

# Terminal 2 — Source 3 consumer : topic taux-change → PostgreSQL
python kafka/consumers/exchange_rate_consumer.py

# Terminal 3 — Source 1 producer : paiements Wave/Orange Money
python kafka/producers/paiement_producer.py

# Terminal 4 — Source 1 consumer : détection anomalies → topic anomalies-paiements
python kafka/consumers/anomaly_consumer.py
```

### . Déclencher le DAG Airflow (pipeline batch)

1. Ouvrir http://localhost:8080
2. Activer `catalogue_produits_batch` (bouton ON)
3. Cliquer sur **▶ Trigger DAG**
4. Suivre les 6 tâches dans **Graph View**

La dernière tâche (`exporter_minio`) publie automatiquement les résultats dans MinIO.

### . Consulter les données

**Marimo (dashboard réactif)** — http://localhost:2718

**Jupyter** — http://localhost:8888 :

```python
import psycopg2, pandas as pd

conn = psycopg2.connect(
    host='postgres', port=5432,
    database='ecommerce_senegal', user='dataeng', password='senegal2024'
)

# Dernières transactions
df = pd.read_sql("SELECT * FROM paiements ORDER BY timestamp_transaction DESC LIMIT 20", conn)

# Anomalies actives
df_ano = pd.read_sql("SELECT * FROM v_anomalies_actives LIMIT 20", conn)

# Stats quotidiennes
df_stats = pd.read_sql("SELECT * FROM stats_quotidiennes ORDER BY date_stats DESC", conn)
```

**MinIO** — http://localhost:9001 → bucket `datalake-senegal` :

```bash
# Export manuel
python scripts/minio_uploader.py
```



---

## Choix Techniques et Justifications

### Apache Kafka — broker de streaming (mode KRaft)

**Choix** : Kafka en mode **KRaft** (sans Zookeeper) plutôt que RabbitMQ ou Redis Pub/Sub.

- **KRaft mode** : Kafka 7.6.0 gère le consensus nativement — suppression du service Zookeeper, stack plus légère et plus moderne (pratique vue en cours)
- **confluent-kafka** (librdkafka) : bibliothèque Python avec delivery callbacks — confirmation de chaque message livré
- **Persistance sur disque** : pas de perte de messages si le consumer redémarre
- **Replay** : possibilité de rejouer les transactions (audit, débogage)
- **Topic dédié anomalies** : `anomalies-paiements` — exigence explicite de l'énoncé
- **Kafbat UI** : interface web pour visualiser les topics, consumer groups et offsets en temps réel

### PostgreSQL — base OLTP

**Choix** : PostgreSQL plutôt que MySQL ou MongoDB.

- **ACID complet** : indispensable pour les transactions financières Wave/Orange Money
- **UPSERT natif** (`ON CONFLICT`) : utilisé dans le DAG Airflow pour le catalogue produits
- **Vues analytiques** : `v_transactions_jour` et `v_anomalies_actives` exposent les données sans duplication

### Apache Airflow — orchestration batch

**Choix** : Airflow plutôt que Cron.

- **DAG versionné** : le pipeline batch est du code, pas une configuration opaque
- **Retry automatique** : si le taux de change n'est pas disponible, Airflow réessaie
- **Visualisation** : Graph View permet de suivre l'état de chaque tâche en temps réel
- **6ème tâche vers MinIO** : le DAG couvre l'intégralité du cycle — ingestion → traitement → stockage

### MinIO — data lake

**Choix** : MinIO plutôt que stockage local.

- **Compatible S3** : même API qu'AWS S3 — migration cloud sans modification du code
- **Chemins partitionnés** : organisation `prefix/year=YYYY/month=MM/day=DD/` inspirée du TP Airflow+MinIO du cours — compatible avec des outils analytiques (Spark, Hive, Athena)
- **Séparation des responsabilités** : PostgreSQL pour le transactionnel, MinIO pour les rapports et snapshots
- **Intégré au DAG Airflow** : la tâche 6 exporte automatiquement après chaque run batch

### Marimo — exposition des données

**Choix** : Marimo (mentionné en premier dans l'énoncé) + Jupyter.

- **Réactivité** : les cellules Marimo se recalculent automatiquement quand les données changent
- **Déployable** : `marimo run` expose le dashboard comme une application web (port 2718)
- **Jupyter** complémentaire : pour l'exploration ad hoc et les analyses one-shot

### Détection d'anomalies — règles métier

**Choix** : règles explicites plutôt que Machine Learning.

- **Transparence** : chaque anomalie a une cause clairement identifiable
- **Pas de données d'entraînement** : ML requiert des mois d'historique labelisé
- **Évolution future** : Isolation Forest ou LSTM quand le volume dépassera 100k transactions

### Docker Compose — infrastructure

**Choix** : Docker Compose plutôt que Kubernetes.

- **Reproductibilité** : `docker-compose up -d` suffit pour déployer les 9 services
- **Approprié** : Kubernetes serait surdimensionné pour moins de 10 services
- **Portabilité** : fonctionne sur Windows, macOS et Linux sans modification

---

## Axes d'Amélioration

### Court terme

1. **Sécurité** : chiffrement des numéros de téléphone (PGP/Fernet), variables sensibles dans HashiCorp Vault, JWT pour exposition API
2. **Monitoring** : intégration Prometheus + Grafana avec alertes Slack si taux d'anomalies > 10 % ou latence Kafka > 1s
3. **Tests automatisés** : pytest pour les fonctions de détection, tests d'intégration consumer/producer, tests du DAG Airflow avec données fictives
4. **API REST** : FastAPI exposant `/api/transactions`, `/api/anomalies`, `/api/stats` avec documentation Swagger automatique

### Moyen terme

5. **Machine Learning** : Isolation Forest (scikit-learn) pour patterns complexes, LSTM pour détecter les comportements inhabituels par client
6. **Optimisation PostgreSQL** : partitionnement par date (`paiements_2026_04`), index bitmap sur colonnes catégoriques, cache Redis pour requêtes fréquentes
7. **Data Quality** : Great Expectations pour valider les données entrantes (format téléphone, cohérence montants, unicité transaction_id)
8. **Kafka Streams** : calculs en fenêtres glissantes (fréquence par client, détection de rafales suspectes)

### Long terme

9. **Migration cloud** : AWS MSK (Kafka managé), RDS (PostgreSQL), MWAA (Airflow managé), S3 (MinIO) via Terraform (Infrastructure as Code)
10. **Data Lakehouse** : remplacement de MinIO par Delta Lake ou Apache Iceberg pour le versioning des données et les requêtes analytiques directes
11. **Compliance** : droit à l'oubli (suppression sur demande), pseudonymisation, logs d'accès aux données sensibles (RGPD)
12. **Multi-tenancy** : isolation par schéma PostgreSQL pour supporter plusieurs marketplaces dans la même infrastructure

---

## Structure du Projet

```
projetdetapipeline/
├── docker-compose.yml               # 8 services Docker
├── .env                             # Variables d'environnement
├── .gitignore
├── requirements.txt                 # Dépendances Python locales
├── README.md
│
├── docker/
│   └── Dockerfile.marimo            # Image custom pour Marimo
│
├── sql/
│   └── schema.sql                   # 5 tables + 2 vues PostgreSQL
│
├── airflow/
│   ├── dags/
│   │   └── catalogue_produits_dag.py  # DAG batch (6 tâches, 2h/nuit)
│   ├── logs/
│   └── plugins/
│
├── kafka/
│   ├── producers/
│   │   ├── paiement_producer.py         # Source 1 : paiements temps réel
│   │   └── exchange_rate_producer.py    # Source 3 : taux de change → Kafka
│   ├── consumers/
│   │   ├── anomaly_consumer.py          # Source 1 : détection + topic anomalies-paiements
│   │   └── exchange_rate_consumer.py    # Source 3 : taux-change → PostgreSQL
│   └── config/
│       └── create_topics.py             # Initialisation des topics
│
├── scripts/
│   ├── anomaly_detection.py           # Module de détection standalone
│   ├── init_db.py                     # Initialisation schéma sans Docker
│   ├── generate_sample_data.py        # Données de test
│   └── minio_uploader.py              # Export vers MinIO
│
├── notebooks/
│   ├── marimo_dashboard.py            # Dashboard réactif (port 2718)
│   └── analyse_donnees.ipynb          # Notebook Jupyter
│
└── data/
    ├── input/
    │   └── catalogue_produits.csv     # Source 2 : catalogue batch
    └── output/
```
