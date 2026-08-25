from dataclasses import dataclass

import neo4j


@dataclass(frozen=True)
class ServiceRef:
    id: str
    name: str


@dataclass(frozen=True)
class QueueRef:
    id: str
    name: str


@dataclass(frozen=True)
class ConsumerWithoutSender:
    consumer_name: str
    queue_id: str
    queue_name: str


_A1_SENDERS = "MATCH (s:Service)-[:SENDS]->(q:Queue {id:$queue_id}) RETURN s.id AS id, s.name AS name ORDER BY s.name"

_A2_CONSUMERS = (
    "MATCH (s:Service)-[:RECEIVES_FROM]->(q:Queue {id:$queue_id}) "
    "RETURN s.id AS id, s.name AS name ORDER BY s.name"
)

_A3_QUEUES_WITHOUT_CONSUMERS = (
    "MATCH (q:Queue) "
    "WHERE EXISTS { MATCH (:Service)-[:SENDS]->(q) } "
    "AND NOT EXISTS { MATCH (:Service)-[:RECEIVES_FROM]->(q) } "
    "RETURN q.id AS id, q.name AS name "
    "ORDER BY q.name"
)

_A4_QUEUES_WITHOUT_SENDERS = (
    "MATCH (consumer:Service)-[:RECEIVES_FROM]->(q:Queue) "
    "WHERE NOT EXISTS { MATCH (:Service)-[:SENDS]->(q) } "
    "RETURN consumer.name AS consumer_name, q.id AS queue_id, q.name AS queue_name "
    "ORDER BY q.name, consumer.name"
)


def senders_of_queue(session: neo4j.Session, queue_id: str) -> list[ServiceRef]:
    """A1 - senders of a queue (spec §13.1)."""
    return [ServiceRef(**record.data()) for record in session.run(_A1_SENDERS, queue_id=queue_id)]


def consumers_of_queue(session: neo4j.Session, queue_id: str) -> list[ServiceRef]:
    """A2 - consumers of a queue (spec §13.2)."""
    return [ServiceRef(**record.data()) for record in session.run(_A2_CONSUMERS, queue_id=queue_id)]


def queues_without_consumers(session: neo4j.Session) -> list[QueueRef]:
    """A3 - queues with a sender but no consumer (spec §13.3)."""
    return [QueueRef(**record.data()) for record in session.run(_A3_QUEUES_WITHOUT_CONSUMERS)]


def queues_without_senders(session: neo4j.Session) -> list[ConsumerWithoutSender]:
    """A4 - consumer queues with no known sender (spec §13.4)."""
    return [
        ConsumerWithoutSender(**record.data()) for record in session.run(_A4_QUEUES_WITHOUT_SENDERS)
    ]
