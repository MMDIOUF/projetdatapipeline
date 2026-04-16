import json
import os
from datetime import datetime

import psycopg2
from confluent_kafka import Consumer, Producer, KafkaError, KafkaException

# Permet de changer le broker (utile si on exécute dans un conteneur Docker).
KAFKA_BROKER = os.getenv('KAFKA_BROKER', 'localhost:9092')
TOPIC_INPUT = 'paiements-senegal'
TOPIC_ANOMALIES = 'anomalies-paiements'

DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'ecommerce_senegal'),
    'user': os.getenv('POSTGRES_USER', 'dataeng'),
    'password': os.getenv('POSTGRES_PASSWORD', 'senegal2024'),
}

MONTANT_SEUIL_MEDIUM = 500_000
MONTANT_SEUIL_HIGH = 1_000_000
MONTANT_ECHEC_SEUIL = 100_000
PAYS_AUTORISES = {'SN', 'ML', 'CI', 'BF', 'GN'}


def detecter_anomalies(txn: dict) -> list[dict]:
    anomalies = []

    if txn['montant'] > MONTANT_SEUIL_MEDIUM:
        severite = 'HIGH' if txn['montant'] > MONTANT_SEUIL_HIGH else 'MEDIUM'
        anomalies.append({
            'type': 'MONTANT_SUSPECT',
            'description': f"Montant {txn['montant']:,.0f} XOF dépasse le seuil de {MONTANT_SEUIL_MEDIUM:,} XOF",
            'severite': severite,
        })

    if txn.get('pays') not in PAYS_AUTORISES:
        anomalies.append({
            'type': 'PAYS_BLOQUE',
            'description': f"Transaction depuis pays non autorisé : {txn.get('pays')}",
            'severite': 'CRITICAL',
        })

    if txn.get('statut') == 'FAILED' and txn['montant'] > MONTANT_ECHEC_SEUIL:
        anomalies.append({
            'type': 'ECHEC_MONTANT_ELEVE',
            'description': f"Échec d'une transaction de {txn['montant']:,.0f} XOF",
            'severite': 'MEDIUM',
        })

    return anomalies


def inserer_paiement(conn, txn: dict):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO paiements (
                transaction_id, montant, devise, methode_paiement,
                numero_telephone, pays, timestamp_transaction,
                statut, client_id, produit_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (transaction_id) DO NOTHING
        """, (
            txn['transaction_id'], txn['montant'], txn['devise'],
            txn['methode_paiement'], txn.get('numero_telephone'),
            txn.get('pays'), txn['timestamp_transaction'],
            txn['statut'], txn.get('client_id'), txn.get('produit_id'),
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f'[ERROR] Insertion paiement : {e}')
    finally:
        cursor.close()


def inserer_anomalie(conn, txn: dict, anomalie: dict):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO anomalies (
            transaction_id, type_anomalie, description,
            montant, methode_paiement, pays, severite
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        txn['transaction_id'], anomalie['type'], anomalie['description'],
        txn['montant'], txn.get('methode_paiement'),
        txn.get('pays'), anomalie['severite'],
    ))
    conn.commit()
    cursor.close()


def delivery_callback(err, msg):
    if err:
        print(f'[ERREUR livraison anomalie] {err}')


def main():
    print('=== Consumer Kafka — Détection d\'Anomalies ===')
    print(f'Consomme : {TOPIC_INPUT}')
    print(f'Anomalies → topic dédié : {TOPIC_ANOMALIES}')
    print('-' * 60)

    consumer = Consumer({
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': 'anomaly-detection-group',
        'auto.offset.reset': 'latest',
        'enable.auto.commit': True,
    })
    consumer.subscribe([TOPIC_INPUT])

    producer_anomalies = Producer({
        'bootstrap.servers': KAFKA_BROKER,
        'acks': 'all',
    })

    conn = psycopg2.connect(**DB_CONFIG)
    print('[OK] Connecté à PostgreSQL')

    nb_traites = 0
    nb_anomalies = 0

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

            txn = json.loads(msg.value().decode('utf-8'))
            nb_traites += 1

            inserer_paiement(conn, txn)

            anomalies = detecter_anomalies(txn)

            if anomalies:
                for anomalie in anomalies:
                    nb_anomalies += 1

                    inserer_anomalie(conn, txn, anomalie)

                    msg_anomalie = {
                        **anomalie,
                        'transaction_id': txn['transaction_id'],
                        'montant': txn['montant'],
                        'methode_paiement': txn.get('methode_paiement'),
                        'pays': txn.get('pays'),
                        'timestamp_detection': datetime.now().isoformat(),
                    }
                    producer_anomalies.produce(
                        topic=TOPIC_ANOMALIES,
                        key=txn['transaction_id'],
                        value=json.dumps(msg_anomalie).encode('utf-8'),
                        callback=delivery_callback,
                    )
                    producer_anomalies.poll(0)

                    print(
                        f'[ANOMALIE] {anomalie["type"]} | '
                        f'sévérité={anomalie["severite"]} | '
                        f'{txn["montant"]:,.0f} XOF'
                    )
            else:
                print(f'[OK] #{nb_traites} — {txn["methode_paiement"]} {txn["montant"]:,.0f} XOF')

    except KeyboardInterrupt:
        print('\nArrêt demandé...')
    except KafkaException as e:
        print(f'[KAFKA ERROR] {e}')
    finally:
        consumer.close()
        producer_anomalies.flush()
        conn.close()
        print(f'\n[RESUME] {nb_traites} transactions | {nb_anomalies} anomalies')


if __name__ == '__main__':
    main()
