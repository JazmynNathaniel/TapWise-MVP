CREATE TABLE IF NOT EXISTS token_blocklist (
  id SERIAL PRIMARY KEY,
  jti VARCHAR(36) NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_token_blocklist_jti ON token_blocklist (jti);
CREATE INDEX IF NOT EXISTS ix_token_blocklist_expires_at ON token_blocklist (expires_at);
