from app.ai.provider import LLMProvider

GRAPH_SCHEMA_DESCRIPTION = """\
Node labels and their key properties:
  Service(id, name, version)
  Operation(id, service_id, operation_id, method, path)
  Queue(id, name, protocol, namespace, queue_type)
  Message(id, name, version, schema_id)
  Schema(id, name, version, format)

Relationship types (always Service/Operation/Queue/Message/Schema as documented):
  (Service)-[:PROVIDES]->(Operation)          REST provider
  (Service)-[:CALLS]->(Operation)              REST caller
  (Operation)-[:REQUEST_SCHEMA]->(Schema)      request payload
  (Operation)-[:RESPONSE_SCHEMA]->(Schema)     response payload
  (Service)-[:SENDS]->(Queue)                  async sender
  (Service)-[:RECEIVES_FROM]->(Queue)          async consumer
  (Queue)-[:CARRIES]->(Message)                message type on queue
  (Message)-[:CONFORMS_TO]->(Schema)           message payload schema
  (Queue)-[:DEAD_LETTERS_TO]->(Queue)          DLQ relationship

Only MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY, and LIMIT are permitted - the \
query must be read-only.\
"""


def generate_cypher(provider: LLMProvider, question: str) -> str:
    """Maps a question + the fixed graph schema (spec §11) to candidate Cypher via the provider."""
    return provider.generate_cypher(question=question, schema_description=GRAPH_SCHEMA_DESCRIPTION)
