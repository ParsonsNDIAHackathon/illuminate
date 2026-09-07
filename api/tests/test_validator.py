import pytest

from illuminate.cypher.validator import CypherRejected, is_pure_create, validate


def test_read_gets_limit():
    v = validate("MATCH (e:Entity) RETURN e")
    assert v.classification == "READ"
    assert v.statement.endswith("LIMIT 500")
    assert "Entity" in v.labels


def test_limit_clamped():
    v = validate("MATCH (e:Entity) RETURN e LIMIT 99999")
    assert v.statement.rstrip().endswith("LIMIT 2000")


def test_existing_limit_kept():
    v = validate("MATCH (e:Entity) RETURN e LIMIT 10")
    assert v.statement.rstrip().endswith("LIMIT 10")


def test_write_classified():
    v = validate("MERGE (e:Entity {id:$id}) SET e.name=$n")
    assert v.classification == "WRITE"


def test_destructive_classified():
    v = validate("MATCH (e:Entity {id:$id}) DETACH DELETE e")
    assert v.classification == "DESTRUCTIVE"
    assert validate("MATCH (e:Entity) REMOVE e.foo").classification == "DESTRUCTIVE"


def test_schema_classified():
    assert validate("CREATE INDEX foo IF NOT EXISTS FOR (n:Entity) ON (n.x)").classification == "SCHEMA"


@pytest.mark.parametrize(
    "q",
    [
        "CALL db.labels()",
        "CALL dbms.components()",
        "LOAD CSV FROM 'file:///x' AS row RETURN row",
        "CALL apoc.load.json('http://x') YIELD value RETURN value",
        "MATCH (e:Entity) RETURN e; MATCH (p:Person) RETURN p",
        "SHOW USERS",
        "CREATE USER x SET PASSWORD 'y'",
        "CALL apoc.cypher.run('MATCH (n) DETACH DELETE n', {}) YIELD value RETURN value",
        "CALL apoc.periodic.iterate('MATCH (n) RETURN n','DETACH DELETE n',{}) YIELD batches RETURN batches",
    ],
)
def test_blocked(q):
    with pytest.raises(CypherRejected):
        validate(q)


def test_unknown_label_rejected():
    with pytest.raises(CypherRejected) as ei:
        validate("MATCH (u:User) RETURN u")
    assert "User" in str(ei.value)


def test_unknown_rel_rejected():
    with pytest.raises(CypherRejected):
        validate("MATCH (a:Entity)-[:KNOWS]->(b:Entity) RETURN a,b")


def test_map_literal_keys_not_labels():
    v = validate("MATCH (s:Entity)-[r:SUPPLIES {tier: 3, sole_source: true}]->(c:Entity {id: $id}) RETURN s LIMIT 5")
    assert v.labels == {"Entity"}
    assert v.rel_types == {"SUPPLIES"}


def test_varlen_cap():
    validate("MATCH (a:Entity)-[:SUPPLIES*1..3]->(b:Entity) RETURN a,b LIMIT 5")
    with pytest.raises(CypherRejected):
        validate("MATCH (a:Entity)-[:SUPPLIES*]->(b:Entity) RETURN a,b LIMIT 5")
    with pytest.raises(CypherRejected):
        validate("MATCH (a:Entity)-[:SUPPLIES*1..12]->(b:Entity) RETURN a,b LIMIT 5")
    with pytest.raises(CypherRejected):
        validate("MATCH (a:Entity)-[:SUPPLIES*3..]->(b:Entity) RETURN a,b LIMIT 5")


def test_strings_do_not_trigger_keywords():
    v = validate("MATCH (e:Entity) WHERE e.name CONTAINS 'DELETE ME LOAD CSV' RETURN e LIMIT 5")
    assert v.classification == "READ"


def test_apoc_allowlist():
    v = validate("MATCH (e:Entity {id:$id}) CALL apoc.path.subgraphAll(e, {maxLevel:2}) YIELD nodes, relationships RETURN nodes, relationships LIMIT 1")
    assert v.classification == "READ"
    with pytest.raises(CypherRejected):
        validate("MATCH (e:Entity) CALL apoc.export.json.all('x',{}) YIELD file RETURN file")


def test_pure_create():
    assert is_pure_create("MERGE (e:Entity {id:$id}) ON CREATE SET e.name=$n")
    assert not is_pure_create("MERGE (e:Entity {id:$id}) SET e.name=$n")
    assert not is_pure_create("MATCH (e:Entity) DELETE e")
    assert not is_pure_create("MATCH (e:Entity) RETURN e")
