BEGIN;

CREATE TABLE IF NOT EXISTS fetch_cache_schema (
  version integer PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fetch_cache_records (
  namespace varchar(100) NOT NULL,
  identity char(64) NOT NULL,
  record jsonb NOT NULL,
  created_at double precision NOT NULL,
  PRIMARY KEY (namespace, identity)
);

CREATE TABLE IF NOT EXISTS fetch_cache_leases (
  namespace varchar(100) NOT NULL,
  identity char(64) NOT NULL,
  owner varchar(64) NOT NULL,
  fence bigint NOT NULL DEFAULT 0,
  lease_until double precision NOT NULL DEFAULT 0,
  created_at double precision NOT NULL,
  updated_at double precision NOT NULL,
  PRIMARY KEY (namespace, identity)
);

CREATE TABLE IF NOT EXISTS fetch_cache_guards (
  namespace varchar(100) NOT NULL,
  identity char(64) NOT NULL,
  lock_version bigint NOT NULL DEFAULT 0,
  PRIMARY KEY (namespace, identity)
);

DO $migration$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fetch_cache_records_valid') THEN
    ALTER TABLE fetch_cache_records ADD CONSTRAINT fetch_cache_records_valid
      CHECK (identity ~ '^[a-f0-9]{64}$' AND jsonb_typeof(record)='object' AND created_at > 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fetch_cache_leases_valid') THEN
    ALTER TABLE fetch_cache_leases ADD CONSTRAINT fetch_cache_leases_valid
      CHECK (identity ~ '^[a-f0-9]{64}$' AND fence >= 0 AND created_at > 0 AND updated_at > 0);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fetch_cache_guards_valid') THEN
    ALTER TABLE fetch_cache_guards ADD CONSTRAINT fetch_cache_guards_valid
      CHECK (identity ~ '^[a-f0-9]{64}$' AND lock_version >= 0);
  END IF;
END
$migration$;

REVOKE ALL ON fetch_cache_schema, fetch_cache_records,
  fetch_cache_leases, fetch_cache_guards FROM PUBLIC;

INSERT INTO fetch_cache_schema(version) VALUES (1) ON CONFLICT DO NOTHING;

COMMIT;