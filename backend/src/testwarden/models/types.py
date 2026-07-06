from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# Portable JSON: plain JSON on SQLite, JSONB on Postgres.
PortableJSON = JSON().with_variant(JSONB(), "postgresql")
