"""Manage SQLite connections, schema, and transactions.

Place the database on a persistent volume. Define foreign keys,
owner-scoped uniqueness constraints, and transactions for state, index,
and budget updates.

Keep read and write transactions short. Make provider calls outside
transactions and commit the results while the associated resources
remain valid.
"""
