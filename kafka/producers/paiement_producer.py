import json
import os
import random
import time
import uuid
from datetime import datetime

from confluent_kafka import Producer, KafkaException
from faker import Faker

# Permet de changer le broker (utile si on exécute dans un conteneur Docker).
KAFKA_BROKER = os.getenv('KAFKA_BROKER', 'localhost:9092')
TOPIC = 'paiements-senegal'

fake = Faker('fr_FR')

METHODES = ['WAVE', 'ORANGE_MONEY']
PREFIXES_SN = ['77', '78', '76', '70']
PAYS = ['SN', 'SN', 'SN', 'SN', 'ML', 'CI', 'BF', 'GN']
CATEGORIES = [
    'Electronique', 'Mode', 'Alimentation', 'Maison',
    'Sport', 'Beaute', 'Livres', 'Telephonie',
]


def delivery_callback(err, msg):
    if err:
        print(f'[ERREUR livraison] {err}')
    else:
        print(
            f'[OK] Msg -> topic={msg.topic()} '
            f'partition={msg.partition()} offset={msg.offset()}'
        )


def generer_numero_telephone():
    prefix = random.choice(PREFIXES_SN)
    return f"+221{prefix}{random.randint(1000000, 9999999)}"


def generer_transaction() -> dict:
    montant = round(random.uniform(1_000, 500_000), 2)

    if random.random() < 0.05:
        montant = round(random.uniform(1_000_000, 5_000_000), 2)

    return {
        'transaction_id': str(uuid.uuid4()),
        'montant': montant,
        'devise': 'XOF',
        'methode_paiement': random.choice(METHODES),
        'numero_telephone': generer_numero_telephone(),
        'pays': random.choice(PAYS),
        'timestamp_transaction': datetime.now().isoformat(),
        'statut': random.choices(
            ['SUCCESS', 'FAILED', 'PENDING'],
            weights=[0.90, 0.05, 0.05],
        )[0],
        'client_id': f'CLIENT_{fake.numerify("####")}',
        'produit_id': f'PROD_{random.randint(100, 120)}',
    }


def main():
    print('=== Producer Kafka — Paiements E-commerce Sénégal ===')
    print(f'Broker : {KAFKA_BROKER} | Topic : {TOPIC}')
    print('-' * 60)

    producer = Producer({
        'bootstrap.servers': KAFKA_BROKER,
        'acks': 'all',
        'retries': 3,
        'retry.backoff.ms': 500,
    })

    nb = 0
    try:
        while True:
            txn = generer_transaction()

            producer.produce(
                topic=TOPIC,
                key=txn['client_id'],
                value=json.dumps(txn).encode('utf-8'),
                callback=delivery_callback,
            )
            producer.poll(0)

            nb += 1
            print(
                f'[ENVOYE #{nb}] {txn["methode_paiement"]} | '
                f'{txn["montant"]:,.0f} XOF | statut={txn["statut"]} | '
                f'pays={txn["pays"]}'
            )
            time.sleep(random.uniform(1, 3))

    except KeyboardInterrupt:
        print('\nArrêt demandé...')
    except KafkaException as e:
        print(f'[KAFKA ERROR] {e}')
    finally:
        producer.flush()
        print(f'\n[OK] {nb} transactions envoyées — producer fermé proprement')


if __name__ == '__main__':
    main()
