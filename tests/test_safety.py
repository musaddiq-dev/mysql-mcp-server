import pytest

from mysql_mcp_server.server import execute_read_query, validate_identifier


def test_validate_identifier_accepts_simple_names():
    assert validate_identifier("users_2026") == "users_2026"


@pytest.mark.parametrize("identifier", ["users`", "users;drop", "public.users", "users-name", ""])
def test_validate_identifier_rejects_unsafe_names(identifier):
    with pytest.raises(ValueError):
        validate_identifier(identifier, "table name")


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE users SET name = 'x'",
        "SELECT * FROM users INTO OUTFILE '/tmp/users.csv'",
        "SELECT LOAD_FILE('/etc/passwd')",
        "SELECT * FROM users; SELECT * FROM secrets",
    ],
)
def test_execute_read_query_rejects_unsafe_sql_before_connection(query):
    with pytest.raises(ValueError):
        execute_read_query(query)
