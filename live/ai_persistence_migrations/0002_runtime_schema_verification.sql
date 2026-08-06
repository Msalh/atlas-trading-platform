-- Phase 18H-1: expose only immutable ledger identity fields to the writer.
GRANT SELECT (filename, sha256)
ON public.atlas_ai_persistence_schema_migrations
TO atlas_ai_persistence_writer;
