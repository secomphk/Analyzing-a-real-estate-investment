-- Idempotent PostGIS bootstrap. Compose mounts this into the
-- postgres entrypoint so a fresh volume is ready for GeoAlchemy2.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
