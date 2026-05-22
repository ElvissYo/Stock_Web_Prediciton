from kag.config import DEFAULT_NEO4J_DATABASE, Settings


def test_settings_loads_required_values_from_env(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.delenv("NEO4J_DATABASE", raising=False)

    settings = Settings.from_env(env_file=None)

    assert settings.neo4j_uri == "bolt://localhost:7687"
    assert settings.neo4j_username == "neo4j"
    assert settings.neo4j_password == "secret"
    assert settings.neo4j_database == DEFAULT_NEO4J_DATABASE


def test_redacted_settings_hide_password(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    settings = Settings.from_env(env_file=None)

    assert settings.redacted()["neo4j_password"] == "***"

