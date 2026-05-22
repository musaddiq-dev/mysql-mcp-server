<!-- mcp-name: io.github.musaddiq-dev/mysql-mcp-server -->
# MySQL MCP Server

A Python Model Context Protocol (MCP) server for inspecting and querying MySQL databases from MCP-compatible clients. It provides table discovery, schema inspection, read query execution, DDL lookup, query explanation, and optional write/DDL tools for controlled database administration workflows.

## Features

- List tables and describe table schemas
- Execute SELECT queries with safety checks
- Retrieve `SHOW CREATE TABLE` output
- Explain query execution plans
- Summarize tables and row counts
- Optional write and DDL tools for users who intentionally run with elevated database privileges

## Safety Model

`mysql_execute_read_query` only accepts a single statement beginning with `SELECT`, rejects common modifying SQL keywords and risky file-read/write forms, and caps returned rows by `MYSQL_READ_QUERY_LIMIT`. This is a guardrail, not a substitute for database permissions. Use a dedicated read-only MySQL user for safe exploration. The write and DDL tools can modify or destroy data if the configured database user is allowed to do so; keep them on manual approval in your MCP client.

## Requirements

- Python 3.11+
- MySQL 5.7+ or MySQL 8.0+
- MCP-compatible client such as Claude Desktop, Cursor, VS Code, or another MCP host

## Installation

When published to PyPI, install or run the server like a standard Python MCP package:

```bash
uvx mdev-mysql-mcp-server
```

For local development from source:

```bash
git clone https://github.com/musaddiq-dev/mysql-mcp-server.git
cd mysql-mcp-server
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configuration

Copy the example environment file and update it with your database connection details.

```bash
cp .env.example .env
```

| Variable | Description | Required | Default |
| --- | --- | --- | --- |
| `MYSQL_HOST` | MySQL host | No | `localhost` |
| `MYSQL_PORT` | MySQL port | No | `3306` |
| `MYSQL_USER` | MySQL username | No | `root` |
| `MYSQL_PASSWORD` | MySQL password | No | Empty |
| `MYSQL_DATABASE` | MySQL database name | Yes | Empty |
| `MYSQL_POOL_SIZE` | Connection pool size | No | `5` |
| `LOG_LEVEL` | Python logging level | No | `INFO` |
| `MYSQL_READ_QUERY_LIMIT` | Maximum rows returned by read queries | No | `1000` |

Example read-only user:

```sql
CREATE USER 'mcp_readonly'@'localhost' IDENTIFIED BY 'change-me';
GRANT SELECT ON your_database.* TO 'mcp_readonly'@'localhost';
FLUSH PRIVILEGES;
```

## Running

```bash
mdev-mysql-mcp-server
```

From a local checkout before PyPI publication, run:

```bash
python -m mysql_mcp_server.server
```

## MCP Client Configuration

For published installs, prefer `uvx`. MCP servers using stdio must write protocol messages only to stdout; this server writes logs to stderr through Python logging.

### Claude Desktop / Cursor / Windsurf / Cline

Most MCP clients accept this `mcpServers` JSON shape:

```json
{
  "mcpServers": {
    "mysql": {
      "command": "uvx",
      "args": ["mdev-mysql-mcp-server"],
      "env": {
        "MYSQL_HOST": "localhost",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "mcp_readonly",
        "MYSQL_PASSWORD": "change-me",
        "MYSQL_DATABASE": "your_database"
      }
    }
  }
}
```

For local development from this repository, use the installed console script path instead:

```json
{
  "mcpServers": {
    "mysql": {
      "command": "/absolute/path/to/mysql-mcp-server/.venv/bin/mdev-mysql-mcp-server",
      "args": [],
      "env": {
        "MYSQL_HOST": "localhost",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "mcp_readonly",
        "MYSQL_PASSWORD": "change-me",
        "MYSQL_DATABASE": "your_database"
      }
    }
  }
}
```

### Claude Code CLI

```bash
claude mcp add mysql \
  --env MYSQL_HOST=localhost \
  --env MYSQL_PORT=3306 \
  --env MYSQL_USER=mcp_readonly \
  --env MYSQL_PASSWORD=change-me \
  --env MYSQL_DATABASE=your_database \
  -- uvx mdev-mysql-mcp-server
```

### VS Code MCP

VS Code uses the same command/args/env model in its MCP configuration:

```json
{
  "servers": {
    "mysql": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mdev-mysql-mcp-server"],
      "env": {
        "MYSQL_HOST": "localhost",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "mcp_readonly",
        "MYSQL_PASSWORD": "change-me",
        "MYSQL_DATABASE": "your_database"
      }
    }
  }
}
```

## Tools

| Tool | Purpose | Safety |
| --- | --- | --- |
| `mysql_list_tables` | List tables in the configured database | Read-only |
| `mysql_describe_table` | Show schema for a table | Read-only |
| `mysql_execute_read_query` | Execute a single bounded SELECT query | Read-only guardrail |
| `mysql_execute_write_query` | Execute a single INSERT, UPDATE, or DELETE | Destructive |
| `mysql_execute_ddl` | Execute a single CREATE, DROP, ALTER, or TRUNCATE | Destructive |
| `mysql_get_table_ddl` | Return `SHOW CREATE TABLE` output | Read-only |
| `mysql_explain_query` | Run `EXPLAIN` for a single query | Read-only |
| `mysql_get_database_summary` | Return table list and row counts | Read-only |

## Smoke Check

Without a database, verify syntax with:

```bash
python -m py_compile src/mysql_mcp_server/server.py
```

With a configured database, start the server and use your MCP client to call `list_tables`.

## Distribution

This repository is prepared for the common Python MCP distribution path: publish the package to PyPI, keep the `mcp-name` marker at the top of this README for MCP Registry ownership verification, and publish `server.json` metadata with the GitHub repository. After release, users should prefer `uvx mdev-mysql-mcp-server` in local MCP client configurations.

## Security Notes

- Do not commit `.env` or MCP client configs containing credentials.
- Use least-privilege database users.
- Keep `execute_write_query` and `execute_ddl` on explicit manual approval.
- Do not expose this server over an untrusted network without additional authentication and transport security.

## License

MIT
