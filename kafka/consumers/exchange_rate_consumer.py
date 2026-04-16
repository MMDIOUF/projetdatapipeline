import json
import os
from datetime import datetime

import psycopg2
from confluent_kafka import Consumer, KafkaError, KafkaException

# Permet de changer le broker (utile si on exécute dans un conteneur Docker).
KAFKA_BROKER = os.getenv('KAFKA_BROKER', 'localhost:9092')
TOPIC = 'taux-change'

DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'ecommerce_senegal'),
    'user': os.getenv('POSTGRES_USER', 'dataeng'),
    'password': os.getenv('POSTGRES_PASSWORD', 'senegal2024'),
}


def inserer_taux(conn, message: dict):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO taux_change (
                devise_source, devise_cible, taux, timestamp_collecte, source
            ) VALUES (%s, %s, %s, %s, %s)
        """, (
            message.get('devise_source', 'XOF'),
            message.get('devise_cible', 'USD'),
            message['taux'],
            message.get('timestamp', datetime.now().isoformat()),
            message.get('source', 'Kafka'),
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f'[ERROR] Insertion taux : {e}')
    finally:
        cursor.close()


def main():
    print('=== Consumer Kafka — Taux de change XOF/USD ===')
    print(f'Topic consommé : {TOPIC}')
    print('Persistance vers : PostgreSQL → table taux_change')
    print('-' * 60)

    consumer = Consumer({
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': 'exchange-rate-consumer-group',
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': True,
    })
    consumer.subscribe([TOPIC])

    conn = psycopg2.connect(**DB_CONFIG)
    print('[OK] Connecté à PostgreSQL')

    nb = 0
    try:
        while True:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                print(f'[KAFKA ERROR] {msg.error()}')
                continue

            data = json.loads(msg.value().decode('utf-8'))
            inserer_taux(conn, data)

            nb += 1
            print(
                f'[OK] #{nb} — 1 XOF = {data["taux"]} USD '
                f'(≈ {data.get("taux_inverse", "?")} XOF/USD) '
                f'| source={data.get("source")}'
            )

    except KeyboardInterrupt:
        print('\nArrêt demandé...')
    except KafkaException as e:
        print(f'[KAFKA ERROR] {e}')
    finally:
        consumer.close()
        conn.close()
        print(f'[OK] {nb} taux persistés en base — consumer fermé proprement')


if __name__ == '__main__':
    main()
