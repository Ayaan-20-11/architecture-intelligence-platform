import neo4j


def build_driver(uri: str, user: str, password: str) -> neo4j.Driver:
    return neo4j.GraphDatabase.driver(uri, auth=(user, password))


def open_session(driver: neo4j.Driver, *, database: str, read_only: bool = False) -> neo4j.Session:
    """Opens a session scoped to the given access mode (spec §19: read-write import user vs read-only analysis/LLM user)."""
    access_mode = neo4j.READ_ACCESS if read_only else neo4j.WRITE_ACCESS
    return driver.session(database=database, default_access_mode=access_mode)
