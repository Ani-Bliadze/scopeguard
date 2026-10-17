-- ScopeGuard synthetic fixture. All values are fictional.
CREATE TABLE customers (
  id INTEGER PRIMARY KEY,
  region TEXT NOT NULL,
  display_name TEXT NOT NULL,
  email TEXT NOT NULL,
  synthetic_personal_id TEXT NOT NULL,
  note TEXT NOT NULL
);
CREATE TABLE sales (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  amount_cents INTEGER NOT NULL,
  month TEXT NOT NULL
);
CREATE TABLE credential_digests (
  connector TEXT PRIMARY KEY,
  expected_sha256 TEXT NOT NULL
);
CREATE TABLE fixture_meta (
  schema_version TEXT NOT NULL,
  seed INTEGER NOT NULL,
  customer_count INTEGER NOT NULL,
  sales_count INTEGER NOT NULL
);
CREATE INDEX idx_sales_month_customer ON sales(month, customer_id);
CREATE INDEX idx_customers_region ON customers(region);
