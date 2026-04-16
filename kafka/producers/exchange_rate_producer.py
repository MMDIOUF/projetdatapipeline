import json
import os
import random
import time
from datetime import datetime

from confluent_kafka import Producer, KafkaException

# Permet de changer le broker (utile si on exécute dans un conteneur Docker).
KAFKA_BROKER = os.getenv('KAFKA_BROKER', 'localhost:9092')
TOPIC = 'taux-change'

TAUX_BASE = 0.00167


def delivery_callback(err, msg):
    if err:
        print(f'[ERREUR livraison] {err}')
    else:
        print(f'[OK] Taux publié -> partition={msg.partition()} offset={msg.offset()}')


def simuler_taux() -> float:
    variation = random.uniform(-0.02, 0.02)
    return round(TAUX_BASE * (1 + variation), 6)


def main():
    # NOTE: evite les caracteres Unicode qui peuvent casser l'encodage console Windows.
    print('=== Producer Kafka - Taux de change XOF/USD ===')
    print(f'Broker : {KAFKA_BROKER} | Topic : {TOPIC}')
    print('Fréquence : toutes les 60 secondes')
    print('-' * 60)

    producer = Producer({
        'bootstrap.servers': KAFKA_BROKER,
        'acks': 'all',
    })

    nb = 0
    try:
        while True:
            taux = simuler_taux()
            message = {
                'devise_source': 'XOF',
                'devise_cible': 'USD',
                'taux': taux,
                'taux_inverse': round(1 / taux, 2),
                'timestamp': datetime.now().isoformat(),
                'source': 'API-Simulation',
            }

            producer.produce(
                topic=TOPIC,
                key='XOF-USD',
                value=json.dumps(message).encode('utf-8'),
                callback=delivery_callback,
            )
            producer.poll(0)

            nb += 1
            # Remplace le symbole unicode "≈" par "~" (ASCII).
            print(f'[#{nb}] 1 XOF = {taux} USD  (~ {1/taux:.0f} XOF/USD)')
            time.sleep(60)

    except KeyboardInterrupt:
        print('\nArrêt demandé...')
    except KafkaException as e:
        print(f'[KAFKA ERROR] {e}')
    finally:
        producer.flush()
        print(f'[OK] {nb} taux publiés — producer fermé proprement')


if __name__ == '__main__':
    main()
