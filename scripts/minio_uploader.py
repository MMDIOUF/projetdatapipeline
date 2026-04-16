import io
import json
import os
from datetime import date, datetime

import pandas as pd
import psycopg2
from minio import Minio

MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'localhost:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ROOT_USER', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin')
BUCKET = os.getenv('MINIO_BUCKET', 'datalake-senegal')

DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'ecommerce_senegal'),
    'user': os.getenv('POSTGRES_USER', 'dataeng'),
    'password': os.getenv('POSTGRES_PASSWORD', 'senegal2024'),
}


def partition_path(prefix: str, today: date, filename: str) -> str:
    return (
        f"{prefix}/"
        f"year={today.year}/"
        f"month={today.month:02d}/"
        f"day={today.day:02d}/"
        f"{filename}"
    )


def get_minio_client() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )


def ensure_bucket(client: Minio):
    if not client.bucket_exists(BUCKET):
        client.make_bucket(BUCKET)
        print(f'[OK] Bucket créé : {BUCKET}')


def upload(client: Minio, data: bytes, object_name: str, content_type: str):
    buf = io.BytesIO(data)
    client.put_object(BUCKET, object_name, buf, length=len(data), content_type=content_type)
    print(f'[OK] → {BUCKET}/{object_name}  ({len(data):,} octets)')


def export_paiements(conn, client: Minio, today: date):
    df = pd.read_sql("""
        SELECT transaction_id, montant, devise, methode_paiement,
               pays, timestamp_transaction, statut, client_id, produit_id
        FROM paiements
        WHERE DATE(timestamp_transaction) = CURRENT_DATE
        ORDER BY timestamp_transaction
    """, conn)

    path = partition_path('paiements', today, 'snapshot.csv')
    upload(client, df.to_csv(index=False).encode('utf-8'), path, 'text/csv')
    print(f'   -> {len(df)} paiements exportés')


def export_anomalies(conn, client: Minio, today: date):
    df = pd.read_sql("""
        SELECT transaction_id, type_anomalie, description,
               montant, methode_paiement, pays, severite, timestamp_detection
        FROM anomalies
        WHERE DATE(timestamp_detection) = CURRENT_DATE
        ORDER BY timestamp_detection DESC
    """, conn)

    payload = {
        'date': today.isoformat(),
        'total_anomalies': len(df),
        'par_type': df.groupby('type_anomalie').size().to_dict() if not df.empty else {},
        'par_severite': df.groupby('severite').size().to_dict() if not df.empty else {},
        'anomalies': df.to_dict(orient='records'),
    }

    path = partition_path('anomalies', today, 'rapport.json')
    upload(client, json.dumps(payload, indent=2, default=str).encode('utf-8'), path, 'application/json')
    print(f'   -> {len(df)} anomalies exportées')


def export_stats(conn, client: Minio, today: date):
    df = pd.read_sql("""
        SELECT * FROM stats_quotidiennes WHERE date_stats = CURRENT_DATE
    """, conn)

    if df.empty:
        print('[WARN] Pas de stats quotidiennes — déclencher le DAG Airflow d\'abord')
        return

    path = partition_path('stats', today, 'quotidien.json')
    data = json.dumps(df.to_dict(orient='records'), indent=2, default=str).encode('utf-8')
    upload(client, data, path, 'application/json')


def main():
    today = date.today()
    print(f'=== Export MinIO — {today.isoformat()} ===')

    client = get_minio_client()
    ensure_bucket(client)

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        export_paiements(conn, client, today)
        export_anomalies(conn, client, today)
        export_stats(conn, client, today)
    finally:
        conn.close()

    print(f'[OK] Export terminé — consulter http://localhost:9001')


if __name__ == '__main__':
    main()
