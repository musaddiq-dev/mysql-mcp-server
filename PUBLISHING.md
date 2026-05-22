# Publishing checklist for mdev MCP servers

This workspace contains three public GitHub repos:

- `aws-cli-mcp-server` -> PyPI package `mdev-aws-mcp-server`
- `mysql-mcp-server` -> PyPI package `mdev-mysql-mcp-server`
- `postgresql-mcp-server` -> PyPI package `mdev-postgresql-mcp-server`

## Phase 1: TestPyPI trusted publishing setup

For each package, create a TestPyPI project/trusted publisher for the matching GitHub repo.

Trusted publisher values:

| Package | Owner | Repository | Workflow | Environment |
| --- | --- | --- | --- | --- |
| `mdev-aws-mcp-server` | `musaddiq-dev` | `aws-cli-mcp-server` | `publish-testpypi.yml` | `testpypi` |
| `mdev-mysql-mcp-server` | `musaddiq-dev` | `mysql-mcp-server` | `publish-testpypi.yml` | `testpypi` |
| `mdev-postgresql-mcp-server` | `musaddiq-dev` | `postgresql-mcp-server` | `publish-testpypi.yml` | `testpypi` |

Then run each repo's **Publish to TestPyPI** GitHub Actions workflow manually.

## Phase 2: Test install from TestPyPI

After each TestPyPI publish succeeds:

```bash
uvx --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple mdev-aws-mcp-server
uvx --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple mdev-mysql-mcp-server
uvx --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple mdev-postgresql-mcp-server
```

## Phase 3: PyPI trusted publishing setup

For production PyPI, create trusted publishers with these values:

| Package | Owner | Repository | Workflow | Environment |
| --- | --- | --- | --- | --- |
| `mdev-aws-mcp-server` | `musaddiq-dev` | `aws-cli-mcp-server` | `publish-pypi.yml` | `pypi` |
| `mdev-mysql-mcp-server` | `musaddiq-dev` | `mysql-mcp-server` | `publish-pypi.yml` | `pypi` |
| `mdev-postgresql-mcp-server` | `musaddiq-dev` | `postgresql-mcp-server` | `publish-pypi.yml` | `pypi` |

## Phase 4: Create GitHub release

In each repo:

```bash
gh release create v0.1.0 --title "v0.1.0" --notes "Initial public release"
```

Publishing the release triggers the production PyPI workflow.

## Phase 5: Final user install commands

```bash
uvx mdev-aws-mcp-server
uvx mdev-mysql-mcp-server
uvx mdev-postgresql-mcp-server
```
