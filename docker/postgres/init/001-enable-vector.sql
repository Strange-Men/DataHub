-- The pgvector type must exist before SQLAlchemy creates Vector columns.
CREATE EXTENSION IF NOT EXISTS vector;
