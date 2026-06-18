ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(40) NOT NULL DEFAULT '';

UPDATE users
SET username = CONCAT('tapwise_user_', id)
WHERE username IS NULL OR TRIM(username) = '';

WITH duplicate_usernames AS (
  SELECT
    id,
    ROW_NUMBER() OVER (PARTITION BY LOWER(username) ORDER BY id) AS duplicate_rank
  FROM users
)
UPDATE users
SET username = CONCAT('tapwise_user_', users.id)
FROM duplicate_usernames
WHERE users.id = duplicate_usernames.id
  AND duplicate_usernames.duplicate_rank > 1;

ALTER TABLE users ALTER COLUMN email DROP NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username_unique ON users (username);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash VARCHAR(64) NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id ON password_reset_tokens (user_id);
CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_token_hash ON password_reset_tokens (token_hash);
CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_expires_at ON password_reset_tokens (expires_at);

ALTER TABLE payment_methods DROP COLUMN IF EXISTS identifier_code;
