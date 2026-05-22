from kag.graph.schema import SCHEMA_STATEMENTS, apply_schema


class RecordingClient:
    def __init__(self):
        self.queries = []

    def execute_write(self, query, parameters=None):
        self.queries.append((query, parameters))
        return []


def test_schema_contains_core_constraints_and_indexes():
    joined = "\n".join(SCHEMA_STATEMENTS)

    assert "Stock" in joined
    assert "Sector" in joined
    assert "NewsArticle" in joined
    assert "MacroIndicator" in joined
    assert "PricePoint" in joined


def test_apply_schema_executes_all_statements():
    client = RecordingClient()

    total = apply_schema(client)

    assert total == len(SCHEMA_STATEMENTS)
    assert len(client.queries) == len(SCHEMA_STATEMENTS)

