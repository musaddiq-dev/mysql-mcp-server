# Security Policy

## Supported Versions

Security updates are provided for the latest version on the `main` branch.

## Reporting a Vulnerability

Please report security issues privately by opening a GitHub security advisory or contacting the maintainer through GitHub. Do not open public issues containing credentials, database dumps, AWS account IDs, connection strings, or exploit details.

## Secrets and Credentials

Never commit `.env` files, database passwords, AWS credentials, access keys, private keys, or MCP client configs containing secrets. Use environment variables or your platform's secret manager.

## Runtime Safety

Run this MCP server with least-privilege credentials. For database servers, prefer read-only users unless you explicitly need write tools. For AWS, use scoped IAM roles or profiles and test destructive commands in non-production accounts first.
