"""Stage-7 slug: a rewrite of the same raw entry must not die on its predecessor's slug."""
from pipeline.db import get_connection, init_db
from pipeline.llm_processor import unique_slug


def _seed(conn, slug):
    conn.execute("DELETE FROM trends WHERE slug = ?", (slug,))
    conn.execute(
        "INSERT INTO trends (title_en, slug, source_url, status, created_at) "
        "VALUES (?, ?, ?, 'rejected', datetime('now'))",
        ("Old title", slug, "https://example.com"))


def test_free_slug_is_title_plus_entry_id():
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM trends WHERE slug LIKE 'fresh-story-%'")
    assert unique_slug("Fresh story", 4242) == "fresh-story-4242"


def test_collision_with_retired_predecessor_gets_a_suffix():
    init_db()
    with get_connection() as conn:
        _seed(conn, "same-title-777")
    assert unique_slug("Same title", 777) == "same-title-777-r2"
    with get_connection() as conn:
        _seed(conn, "same-title-777-r2")
    assert unique_slug("Same title", 777) == "same-title-777-r3"
