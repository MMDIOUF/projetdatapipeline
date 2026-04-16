# Commandes & Checklists (triées)

## Table des matières
1. Prérequis
2. Démarrer la stack Docker
3. Vérifications (web + PostgreSQL + Kafka + données de test)
4. Pipeline temps réel (4 terminaux)
5. Vérifier l'ingestion en base
6. Pipeline batch (Airflow DAG)
7. Vérifier MinIO + Dashboards
8. Checklist finale
9. Pousser sur GitHub
10. Commandes de diagnostic
11. Résumé des ports

---
## 1) Prérequis
### Vérifier Docker Desktop
```bash
docker --version
docker compose version
```
> Attendu : Docker >= 24.x, Compose >= 2.x
> Si absent : https://www.docker.com/products/docker-desktop/

### Vérifier Python
```bash
python --version
pip --version
```
> Attendu : Python >= 3.11

### Cloner / se positionner dans le projet
```bash
cd C:\Users\7MAKSACOD\OneDrive\Desktop\projetdetapipeline
```

### Installer les dépendances Python locales
```bash
pip install -r requirements.txt
```

---
## 2) Démarrer la stack Docker
### Lancer les services
```bash
docker compose up -d
```

### Vérifier que tous les services sont UP
```bash
docker compose ps
```
**Résultat attendu (8 services) :**
```text
NAME                 STATUS
kafka                Up (healthy)
kafka-ui             Up
postgres             Up (healthy)
minio                Up (healthy)
airflow-webserver    Up (healthy)
airflow-scheduler    Up
marimo               Up
jupyter              Up
```

> Si un service est `Restarting` ou `Exit` :
```bash
docker compose logs <nom-service>
# Exemples :
docker compose logs kafka
docker compose logs airflow-webserver
```

### Attendre que tout soit prêt (~3-5 min)
```bash
# Vérifier Airflow spécifiquement
docker compose logs airflow-webserver | tail -20
# Attendre de voir : "Listening at: http://0.0.0.0:8080"
```

---
## 3) Vérifications (web + PostgreSQL + Kafka + données de test)
### 3.1 Vérifier les interfaces web
| Service | URL | Identifiants | Ce qu'on doit voir |
|---|---|---|---|
| **Airflow** | http://localhost:8080 | admin / admin | DAG `catalogue_produits_batch` dans la liste |
| **Kafbat UI** | http://localhost:8090 | aucun | Cluster `ecommerce-senegal`, 0 topics au début |
| **MinIO Console** | http://localhost:9001 | minioadmin / minioadmin | Aucun bucket au début |
| **Jupyter** | http://localhost:8888 | aucun | Jupyter Lab vide |
| **Marimo** | http://localhost:2718 | aucun | Dashboard (tables vides au début) |

### 3.2 Vérifier PostgreSQL
```bash
docker exec -it postgres psql -U dataeng -d ecommerce_senegal
```

#### Vérifier que les 5 tables existent
```sql
\dt
```
**Attendu :**
```text
 Schema |        Name         | Type  |  Owner
--------+---------------------+-------+----------
 public | anomalies           | table | dataeng
 public | paiements           | table | dataeng
 public | produits            | table | dataeng
 public | stats_quotidiennes  | table | dataeng
 public | taux_change         | table | dataeng
```

#### Vérifier les 2 vues analytiques
```sql
\dv
```
**Attendu :**
```text
 v_anomalies_actives
 v_transactions_jour
```

#### Vérifier la connexion Airflow `postgres_default`
```bash
docker exec -it airflow-webserver airflow connections get postgres_default
```
**Attendu :** `conn_type=postgres, host=postgres, schema=ecommerce_senegal`

```sql
\q
```

### 3.3 Vérifier les topics Kafka
#### Via Kafbat UI
Aller sur http://localhost:8090 → Topics

#### Via terminal
```bash
docker exec -it kafka kafka-topics --list --bootstrap-server localhost:9092
```

#### Créer les topics explicitement (optionnel, auto-créés)
```bash
python kafka/config/create_topics.py
```
**Attendu :**
```text
[OK] Topic créé : paiements-senegal
[OK] Topic créé : anomalies-paiements
[OK] Topic créé : taux-change
```

### 3.4 Générer des données de test initiales
```bash
python scripts/generate_sample_data.py
```
**Attendu :**
```text
[OK] 200 paiements de test générés
[OK] 30 jours de taux de change générés
[OK] Terminé — base prête pour les tests
```

#### Vérifier en base
```bash
docker exec -it postgres psql -U dataeng -d ecommerce_senegal -c "SELECT COUNT(*) FROM paiements;"
docker exec -it postgres psql -U dataeng -d ecommerce_senegal -c "SELECT COUNT(*) FROM taux_change;"
```
**Attendu :** 200 paiements, 30 taux de change

---
## 4) Pipeline temps réel (4 terminaux)
> Ouvrir 4 terminaux séparés dans le dossier du projet

### Terminal 1 — Source 3 Producer (taux de change → Kafka)
```bash
python kafka/producers/exchange_rate_producer.py
```
**Attendu :**
```text
=== Producer Kafka — Taux de change XOF/USD ===
[#1] 1 XOF = 0.001673 USD  (≈ 598 XOF/USD)
[OK] Taux publié -> partition=0 offset=0
```

### Terminal 2 — Source 3 Consumer (Kafka → PostgreSQL)
```bash
python kafka/consumers/exchange_rate_consumer.py
```
**Attendu :**
```text
[OK] Connecté à PostgreSQL
[OK] #1 — 1 XOF = 0.001673 USD | source=API-Simulation
```

### Terminal 3 — Source 1 Producer (paiements Wave/Orange Money)
```bash
python kafka/producers/paiement_producer.py
```
**Attendu :**
```text
=== Producer Kafka — Paiements E-commerce Sénégal ===
[ENVOYE #1] WAVE | 45 230 XOF | statut=SUCCESS | pays=SN
[OK] Msg -> topic=paiements-senegal partition=0 offset=0
```

### Terminal 4 — Source 1 Consumer (détection anomalies + topic dédié)
```bash
python kafka/consumers/anomaly_consumer.py
```
**Attendu (transactions normales) :**
```text
[OK] #1 — WAVE 45 230 XOF
[OK] #2 — ORANGE_MONEY 12 500 XOF
```

**Attendu (anomalie détectée) :**
```text
[ANOMALIE] MONTANT_SUSPECT | sévérité=HIGH | 1 250 000 XOF
```

### Vérifier que les 3 topics reçoivent des messages
Aller sur http://localhost:8090 → Topics

| Topic | Messages attendus |
|---|---|
| `paiements-senegal` | Croissant (1 toutes les 1-3s) |
| `anomalies-paiements` | ~5% des messages de paiements |
| `taux-change` | 1 message par minute |

---
## 5) Vérifier l'ingestion temps réel en base
```bash
docker exec -it postgres psql -U dataeng -d ecommerce_senegal
```

### Paiements ingérés (doit augmenter pendant que le producer tourne)
```sql
SELECT COUNT(*) FROM paiements;
SELECT transaction_id, montant, methode_paiement, statut, pays
FROM paiements ORDER BY created_at DESC LIMIT 5;
```

### Anomalies détectées (table `anomalies`)
```sql
SELECT COUNT(*) FROM anomalies;
SELECT type_anomalie, severite, montant
FROM anomalies ORDER BY timestamp_detection DESC LIMIT 5;
```

### Taux de change ingérés depuis le topic Kafka
```sql
SELECT COUNT(*) FROM taux_change;
SELECT taux, timestamp_collecte, source
FROM taux_change ORDER BY timestamp_collecte DESC LIMIT 3;
```

```sql
\q
```

---
## 6) Pipeline batch (Airflow DAG)
### Via l'interface web
1. Aller sur http://localhost:8080
2. Login : **admin** / **admin**
3. Trouver `catalogue_produits_batch`
4. Cliquer sur le toggle **ON/OFF** → le passer en **ON** (bleu)
5. Cliquer sur **▶ (Trigger DAG)** → **Trigger DAG**
6. Cliquer sur le DAG → **Graph View**

**Les 6 tâches doivent devenir vertes dans l'ordre :**
```text
lire_catalogue → obtenir_taux_change → calculer_prix_usd → inserer_produits → generer_stats → exporter_minio
```

### Via terminal (alternative)
```bash
docker exec -it airflow-webserver airflow dags trigger catalogue_produits_batch
```

### Vérifier les résultats du DAG en base
```bash
docker exec -it postgres psql -U dataeng -d ecommerce_senegal
```
```sql
-- Catalogue enrichi avec prix USD
SELECT produit_id, nom, prix_xof, prix_usd FROM produits LIMIT 5;

-- Stats quotidiennes générées
SELECT * FROM stats_quotidiennes ORDER BY date_stats DESC LIMIT 3;
```
```sql
\q
```

---
## 7) Vérifier MinIO + Dashboards
### 7.1 Vérifier MinIO (data lake)
#### Via l'interface web
1. Aller sur http://localhost:9001
2. Login : **minioadmin** / **minioadmin**
3. Vérifier le bucket `datalake-senegal`
4. Naviguer dans les dossiers :
   - `batch/year=2026/month=04/day=16/catalogue.csv`
   - `batch/year=2026/month=04/day=16/stats.json`

#### Via terminal (export manuel si le DAG a tourné)
```bash
python scripts/minio_uploader.py
```

**Attendu :**
```text
=== Export MinIO — 2026-04-16 ===
[OK] → datalake-senegal/paiements/year=2026/month=04/day=16/snapshot.csv
[OK] → datalake-senegal/anomalies/year=2026/month=04/day=16/rapport.json
[OK] → datalake-senegal/stats/year=2026/month=04/day=16/quotidien.json
```

#### Vérifier via CLI MinIO (`mc`)
```bash
docker exec -it minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker exec -it minio mc ls local/datalake-senegal --recursive
```

### 7.2 Vérifier l'exposition des données
#### Marimo — Dashboard réactif
1. Aller sur http://localhost:2718
2. Ce qu'on doit voir :
   - KPIs : total transactions, montant total, nb anomalies
   - Table Wave vs Orange Money
   - Table des 20 dernières anomalies
   - Table stats quotidiennes (après le DAG)
   - Table des taux de change

#### Jupyter — Notebook d'analyse
1. Aller sur http://localhost:8888
2. Ouvrir `work/analyse_donnees.ipynb`
3. Run All (Kernel → Restart & Run All)
4. Ce qu'on doit voir :
   - Cellule 1 : `Connexion PostgreSQL OK`
   - Cellule 2 : Tableau statistiques globales
   - Cellule 3 : Graphe camembert Wave vs Orange Money
   - Cellule 4 : Barplot anomalies par type
   - Cellule 5 : Courbe transactions dans le temps
   - Cellule 6 : Courbe taux de change
   - Cellule 7 : Tableau catalogue produits avec prix USD

---
## 8) Checklist finale
Vérifier chaque point avant de soumettre :

### Sources de données (minimum 3)
- [ ] **Source 1 temps réel** : le producer envoie des paiements sur `paiements-senegal`
- [ ] **Source 2 batch** : le DAG lit `data/input/catalogue_produits.csv`
- [ ] **Source 3 choix** : le producer envoie des taux sur `taux-change`

### Ingestion
- [ ] Source 1 ingérée : `SELECT COUNT(*) FROM paiements;` > 0
- [ ] Source 2 ingérée : `SELECT COUNT(*) FROM produits;` = 20
- [ ] Source 3 ingérée : `SELECT COUNT(*) FROM taux_change;` > 0

### Traitement
- [ ] **Anomalies temps réel** : `SELECT COUNT(*) FROM anomalies;` > 0
- [ ] **Topic dédié anomalies** : topic `anomalies-paiements` visible dans Kafbat UI avec messages
- [ ] **Batch quotidien** : DAG Airflow terminé en vert (6 tâches)

### Exposition
- [ ] Marimo accessible http://localhost:2718 avec données
- [ ] Jupyter accessible http://localhost:8888 avec notebook fonctionnel
- [ ] MinIO http://localhost:9001 avec fichiers dans le bucket

### Docker
- [ ] `docker compose ps` → 8 services `Up`

### README (6 sections obligatoires)
- [ ] Objectif du projet
- [ ] Process suivi
- [ ] Stack technique utilisée
- [ ] Instructions de déploiement
- [ ] Choix techniques et leur justification
- [ ] Axes d'amélioration

---
## 9) Pousser sur GitHub
```bash
cd C:\Users\7MAKSACOD\OneDrive\Desktop\projetdetapipeline

git init
git add .
git status
# Vérifier que catalogue_produits.csv EST bien dans la liste (pas ignoré)
# Vérifier que .env N'EST PAS dans la liste (ignoré)

git commit -m "feat: plateforme data pipelines e-commerce Senegal - Kafka + Airflow + PostgreSQL + MinIO + Marimo"
git remote add origin https://github.com/TON-USERNAME/projet-datapipelines-senegal.git
git branch -M main
git push -u origin main
```

> Si Git demande un token : https://github.com/settings/tokens → Generate new token (classic) → cocher `repo` → copier le token comme mot de passe

### Vérifier sur GitHub
- [ ] Le `README.md` s'affiche correctement avec toutes les sections
- [ ] `Projet_DataPipelines_DSIA.pdf` est visible dans le repo
- [ ] `docker-compose.yml` est présent
- [ ] `data/input/catalogue_produits.csv` est présent (pas ignoré par git)
- [ ] `.env` N'EST PAS visible (ignoré par .gitignore)

---
## 10) Commandes de diagnostic
### Kafka ne démarre pas
```bash
docker compose logs kafka | tail -30
# Si "CLUSTER_ID mismatch" : supprimer le volume et redémarrer
docker compose down -v
docker compose up -d
```

### Airflow DAG en rouge
```bash
# Voir les logs de la tâche en erreur
docker exec -it airflow-webserver airflow tasks test catalogue_produits_batch lire_catalogue 2026-04-16
```

### Consumer Python ne se connecte pas à Kafka
```bash
# Vérifier que Kafka écoute bien sur 9092
docker exec -it kafka kafka-broker-api-versions --bootstrap-server localhost:9092
```

### PostgreSQL : refus de connexion
```bash
docker compose logs postgres | tail -10
docker exec -it postgres pg_isready -U dataeng
```

### MinIO inaccessible
```bash
curl http://localhost:9000/minio/health/live
```

### Tout réinitialiser (ATTENTION : efface les données)
```bash
docker compose down -v
docker compose up -d
python scripts/generate_sample_data.py
```

---
## 11) Résumé des ports
| Port | Service | URL |
|---|---|---|
| 8080 | Airflow UI | http://localhost:8080 |
| 8090 | Kafbat UI (topics Kafka) | http://localhost:8090 |
| 8888 | Jupyter Lab | http://localhost:8888 |
| 9000 | MinIO API | — |
| 9001 | MinIO Console | http://localhost:9001 |
| 9092 | Kafka Broker | `localhost:9092` |
| 5432 | PostgreSQL | `localhost:5432` |
| 2718 | Marimo Dashboard | http://localhost:2718 |

