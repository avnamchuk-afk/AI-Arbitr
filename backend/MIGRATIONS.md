# Database migrations

Alembic starts from the schema already used by AI-Arbitr production.

## Existing installation

Do not run `upgrade` before verifying that the existing schema matches revision `20260927_0001`.

1. Create and verify a PostgreSQL backup.
2. Run the migration smoke test against an isolated database.
3. Stamp the existing schema once:

```bash
alembic -c alembic.ini stamp 20260927_0001
```

4. Apply the additive Agreement foundation migration:

```bash
alembic -c alembic.ini upgrade head
```

5. Verify the current revision:

```bash
alembic -c alembic.ini current
```

Revision `20260927_0002` only adds columns, indexes, foreign keys, and new tables. It does not rename or remove existing objects.

## New development database

The application still creates the current ORM schema for isolated tests and an empty development database. Alembic becomes the only supported mechanism for changing an existing production schema.
