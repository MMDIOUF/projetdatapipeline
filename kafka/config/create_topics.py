from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka.error import KafkaException

KAFKA_BROKER = 'localhost:9092'

TOPICS = [
    NewTopic('paiements-senegal',  num_partitions=3, replication_factor=1),
    NewTopic('anomalies-paiements', num_partitions=1, replication_factor=1),
    NewTopic('taux-change',         num_partitions=1, replication_factor=1),
]


def create_topics():
    admin = AdminClient({'bootstrap.servers': KAFKA_BROKER})

    fs = admin.create_topics(TOPICS)

    for topic, future in fs.items():
        try:
            future.result()
            print(f'[OK] Topic créé : {topic}')
        except KafkaException as e:
            if 'TopicExistsException' in str(e) or 'already exists' in str(e).lower():
                print(f'[INFO] Topic existe déjà : {topic}')
            else:
                print(f'[ERROR] {topic} : {e}')


if __name__ == '__main__':
    create_topics()
