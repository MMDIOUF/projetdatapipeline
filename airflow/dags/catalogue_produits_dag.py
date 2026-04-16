import io
import json
import os
from datetime import datetime, timedelta, date

import pandas as pd
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

default_args = {
    'owner': 'dataeng-senegal',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'minio:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ROOT_USER', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin')
BUCKET = os.getenv('MINIO_BUCKET', 'datalake-senegal')


def lire_catalogue_csv(**context):
    csv_path = '/opt/airflow/data/input/catalogue_produits.csv'

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Fichier introuvable : {csv_path}")

    df = pd.read_csv(csv_path)
    print(f"[OK] {len(df)} produits lus depuis le CSV")
    context['ti'].xcom_push(key='catalogue_df', value=df.to_json())
    return len(df)


def obtenir_taux_change(**context):
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')

    result = pg_hook.get_first("""
        SELECT taux FROM taux_change
        WHERE devise_source = 'XOF' AND devise_cible = 'USD'
        ORDER BY timestamp_collecte DESC LIMIT 1
    """)

    taux = float(result[0]) if result else 0.00167
    if not result:
        print("[WARN] Aucun taux en base — taux par defaut utilise : 0.00167")
    else:
        print(f"[OK] Taux actuel : 1 XOF = {taux} USD")

    context['ti'].xcom_push(key='taux_xof_usd', value=taux)
    return taux


def calculer_prix_usd(**context):
    catalogue_json = context['ti'].xcom_pull(key='catalogue_df', task_ids='lire_catalogue')
    taux = context['ti'].xcom_pull(key='taux_xof_usd', task_ids='obtenir_taux_change')

    df = pd.read_json(catalogue_json)
    df['prix_usd'] = (df['prix_xof'] * taux).round(2)

    print(f"[OK] Prix USD calcules pour {len(df)} produits (taux={taux})")
    context['ti'].xcom_push(key='catalogue_enrichi', value=df.to_json())
    return len(df)


def inserer_produits_postgres(**context):
    catalogue_json = context['ti'].xcom_pull(key='catalogue_enrichi', task_ids='calculer_prix_usd')
    df = pd.read_json(catalogue_json)

    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    conn = pg_hook.get_conn()
    cursor = conn.cursor()

    nb_inseres = nb_maj = 0

    for _, row in df.iterrows():
        try:
            cursor.execute("""
                INSERT INTO produits (
                    produit_id, nom, categorie, prix_xof, prix_usd,
                    stock, fournisseur, date_ajout, date_maj
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (produit_id) DO UPDATE SET
                    nom = EXCLUDED.nom,
                    categorie = EXCLUDED.categorie,
                    prix_xof = EXCLUDED.prix_xof,
                    prix_usd = EXCLUDED.prix_usd,
                    stock = EXCLUDED.stock,
                    fournisseur = EXCLUDED.fournisseur,
                    date_maj = CURRENT_TIMESTAMP
            """, (
                row['produit_id'], row['nom'], row['categorie'],
                row['prix_xof'], row['prix_usd'], row['stock'],
                row['fournisseur'], row['date_ajout'],
            ))
            nb_inseres += 1
        except Exception as e:
            print(f"[ERROR] {row['produit_id']} : {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"[OK] {nb_inseres} produits traites ({nb_maj} mis a jour)")
    return nb_inseres


def generer_stats_quotidiennes(**context):
    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    pg_hook.run("""
        INSERT INTO stats_quotidiennes (
            date_stats, total_transactions, montant_total_xof, montant_moyen_xof,
            nb_paiements_wave, nb_paiements_orange, nb_anomalies, taux_change_moyen
        )
        SELECT
            CURRENT_DATE,
            COUNT(*),
            COALESCE(SUM(montant), 0),
            COALESCE(AVG(montant), 0),
            SUM(CASE WHEN methode_paiement = 'WAVE' THEN 1 ELSE 0 END),
            SUM(CASE WHEN methode_paiement = 'ORANGE_MONEY' THEN 1 ELSE 0 END),
            (SELECT COUNT(*) FROM anomalies WHERE DATE(timestamp_detection) = CURRENT_DATE),
            (SELECT AVG(taux) FROM taux_change WHERE DATE(timestamp_collecte) = CURRENT_DATE)
        FROM paiements
        WHERE DATE(timestamp_transaction) = CURRENT_DATE
        ON CONFLICT (date_stats) DO UPDATE SET
            total_transactions = EXCLUDED.total_transactions,
            montant_total_xof  = EXCLUDED.montant_total_xof,
            montant_moyen_xof  = EXCLUDED.montant_moyen_xof,
            nb_paiements_wave  = EXCLUDED.nb_paiements_wave,
            nb_paiements_orange = EXCLUDED.nb_paiements_orange,
            nb_anomalies       = EXCLUDED.nb_anomalies,
            taux_change_moyen  = EXCLUDED.taux_change_moyen
    """)
    print("[OK] Statistiques quotidiennes generees")


def exporter_vers_minio(**context):
    from minio import Minio

    today = date.today()

    def partition_path(prefix: str, filename: str) -> str:
        return (
            f"{prefix}/"
            f"year={today.year}/"
            f"month={today.month:02d}/"
            f"day={today.day:02d}/"
            f"{filename}"
        )

    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )
    if not client.bucket_exists(BUCKET):
        client.make_bucket(BUCKET)
        print(f"[OK] Bucket '{BUCKET}' cree")

    def upload(data: bytes, name: str, ctype: str):
        buf = io.BytesIO(data)
        client.put_object(BUCKET, name, buf, length=len(data), content_type=ctype)
        print(f"[OK] {BUCKET}/{name}")

    catalogue_json = context['ti'].xcom_pull(key='catalogue_enrichi', task_ids='calculer_prix_usd')
    df_cat = pd.read_json(catalogue_json)
    upload(
        df_cat.to_csv(index=False).encode('utf-8'),
        partition_path('batch', 'catalogue.csv'),
        "text/csv",
    )

    pg_hook = PostgresHook(postgres_conn_id='postgres_default')
    conn = pg_hook.get_conn()
    df_stats = pd.read_sql(
        "SELECT * FROM stats_quotidiennes WHERE date_stats = CURRENT_DATE", conn
    )
    conn.close()

    payload = df_stats.to_dict(orient='records')
    upload(
        json.dumps(payload, default=str, indent=2).encode('utf-8'),
        partition_path('batch', 'stats.json'),
        "application/json",
    )

    print(f"[OK] Export MinIO termine — batch/year={today.year}/month={today.month:02d}/day={today.day:02d}/")


with DAG(
    'catalogue_produits_batch',
    default_args=default_args,
    description='Pipeline batch quotidien : catalogue produits -> PostgreSQL -> MinIO',
    schedule_interval='0 2 * * *',
    catchup=False,
    tags=['batch', 'ecommerce', 'senegal'],
) as dag:

    t1 = PythonOperator(task_id='lire_catalogue',       python_callable=lire_catalogue_csv)
    t2 = PythonOperator(task_id='obtenir_taux_change',  python_callable=obtenir_taux_change)
    t3 = PythonOperator(task_id='calculer_prix_usd',    python_callable=calculer_prix_usd)
    t4 = PythonOperator(task_id='inserer_produits',     python_callable=inserer_produits_postgres)
    t5 = PythonOperator(task_id='generer_stats',        python_callable=generer_stats_quotidiennes)
    t6 = PythonOperator(task_id='exporter_minio',       python_callable=exporter_vers_minio)

    t1 >> t2 >> t3 >> t4 >> t5 >> t6
