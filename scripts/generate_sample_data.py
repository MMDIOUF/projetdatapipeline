import random
import os
import uuid
from datetime import datetime, timedelta

import psycopg2
from faker import Faker

DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'ecommerce_senegal'),
    'user': os.getenv('POSTGRES_USER', 'dataeng'),
    'password': os.getenv('POSTGRES_PASSWORD', 'senegal2024'),
}

fake = Faker('fr_FR')

METHODES = ['WAVE', 'ORANGE_MONEY']
PAYS_LIST = ['SN', 'ML', 'CI', 'BF']
PREFIXES_SN = ['77', '78', '76', '70']
STATUTS = ['SUCCESS', 'FAILED', 'PENDING']


def generer_paiement() -> dict:
    return {
        'transaction_id': str(uuid.uuid4()),
        'montant': round(random.uniform(1_000, 500_000), 2),
        'devise': 'XOF',
        'methode_paiement': random.choice(METHODES),
        'numero_telephone': f"+221{random.choice(PREFIXES_SN)}{random.randint(1000000, 9999999)}",
        'pays': random.choice(PAYS_LIST),
        'timestamp_transaction': datetime.now() - timedelta(days=random.randint(0, 30)),
        'statut': random.choices(STATUTS, weights=[0.90, 0.05, 0.05])[0],
        'client_id': f'CLIENT_{fake.numerify("####")}',
        'produit_id': f'PROD_{random.randint(100, 120)}',
    }


def inserer_paiements(conn, nb: int = 200):
    cursor = conn.cursor()
    for _ in range(nb):
        p = generer_paiement()
        cursor.execute("""
            INSERT INTO paiements (
                transaction_id, montant, devise, methode_paiement,
                numero_telephone, pays, timestamp_transaction,
                statut, client_id, produit_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            p['transaction_id'], p['montant'], p['devise'],
            p['methode_paiement'], p['numero_telephone'], p['pays'],
            p['timestamp_transaction'], p['statut'],
            p['client_id'], p['produit_id'],
        ))
    conn.commit()
    cursor.close()
    print(f'[OK] {nb} paiements générés')


def inserer_taux_change(conn, nb_jours: int = 30):
    cursor = conn.cursor()
    taux_base = 0.00167
    for i in range(nb_jours):
        taux = round(taux_base * (1 + random.uniform(-0.02, 0.02)), 6)
        ts = datetime.now() - timedelta(days=nb_jours - i)
        cursor.execute("""
            INSERT INTO taux_change (devise_source, devise_cible, taux, timestamp_collecte, source)
            VALUES (%s, %s, %s, %s, %s)
        """, ('XOF', 'USD', taux, ts, 'Historique-Init'))
    conn.commit()
    cursor.close()
    print(f'[OK] {nb_jours} jours de taux de change générés')


def main():
    print('=== Génération de données de test ===')
    conn = psycopg2.connect(**DB_CONFIG)

    inserer_paiements(conn, nb=200)
    inserer_taux_change(conn, nb_jours=30)

    conn.close()
    print('[OK] Terminé — base prête pour les tests')


if __name__ == '__main__':
    main()
