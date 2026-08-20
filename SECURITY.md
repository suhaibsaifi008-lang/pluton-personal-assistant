# Security model

PLUTON begins with a deny-by-default posture:

- Provider keys live in environment configuration and are never exposed by the API.
- File reads validate that paths remain inside the configured workspace.
- Tools carry `low`, `medium`, or `high` permission levels.
- High-risk operations must request explicit confirmation before they execute.
- Database records contain task/memory data only; credentials and cookies are not stored.

Future terminal, browser, and computer adapters must use this same tool registry and permission gate. Destructive filesystem operations, publishing, payments, credential changes, and security changes must always require confirmation.
