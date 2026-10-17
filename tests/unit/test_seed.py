import sqlite3

import pytest

from backend.data.seed import CANARY_PREFIX, amount_cents, build_database, fixture_digest

pytestmark = pytest.mark.unit


def test_fixture_cardinality_and_determinism(tmp_path):
    a, b = tmp_path / "a.sqlite", tmp_path / "b.sqlite"
    counts = build_database(a, CANARY_PREFIX + "_x")
    build_database(b, CANARY_PREFIX + "_y")
    assert counts == {"customers": 5000, "sales": 10000, "regions": 4}
    assert fixture_digest(a) == fixture_digest(b)  # business content is reproducible


def test_fixture_values_are_synthetic_and_credential_is_digest_only(tmp_path):
    db = tmp_path / "f.sqlite"
    build_database(db, CANARY_PREFIX + "_abc")
    con = sqlite3.connect(db)
    regions = {r[0] for r in con.execute("SELECT DISTINCT region FROM customers")}
    assert regions == {"North", "South", "East", "West"}
    row = con.execute("SELECT display_name, email, synthetic_personal_id FROM customers WHERE id=105").fetchone()
    assert row == ("Demo Customer 00105", "customer00105@example.com", "TEST-PID-00105")
    assert con.execute("SELECT COUNT(*) FROM customers WHERE email NOT LIKE '%@example.com'").fetchone()[0] == 0
    dump = "\n".join(con.iterdump())
    assert CANARY_PREFIX not in dump  # only the SHA-256 digest is stored
    assert con.execute("SELECT amount_cents FROM sales WHERE id=5001").fetchone()[0] == amount_cents(1, 1)
    con.close()
