"""Work-type gate for the research tier (#73): the Python classifier, the
repository-host net and the SQL mirror used by build_research_index.py."""
import re

import pytest

from pipeline import research_kinds as rk


@pytest.mark.parametrize("url", [
    "https://doi.org/10.5281/zenodo.22080387",          # Zenodo via DOI (the #73 case)
    "https://zenodo.org/records/22080387",
    "https://doi.org/10.6084/m9.figshare.123",
    "https://datadryad.org/stash/dataset/doi:10.5061/dryad.abc",
    "https://osf.io/abcde/",
    "https://github.com/org/repo",
    "https://gitlab.com/org/repo",
    "https://archive.softwareheritage.org/swh:1:dir:abc",
    "https://dataverse.harvard.edu/dataset.xhtml",
    "https://doi.org/10.7910/DVN/ABCDEF",
    "HTTPS://ZENODO.ORG/record/1",                      # case-insensitive
])
def test_repository_hosts_match(url):
    assert rk.is_repository_url(url)


@pytest.mark.parametrize("url", [
    "https://doi.org/10.1038/s41586-026-00001-1",
    "https://arxiv.org/abs/2609.01234",
    "https://www.sciencedirect.com/science/article/pii/S0001",
    "https://academic.oup.com/x",
    None, "",
])
def test_paper_hosts_pass(url):
    assert not rk.is_repository_url(url)


def test_is_repository_url_checks_every_argument():
    assert rk.is_repository_url("https://example.org/x", "https://doi.org/10.5281/zenodo.1")
    assert not rk.is_repository_url(None, "")


def test_pattern_is_safe_for_the_db_wrapper_and_postgres():
    # pipeline.db rewrites `?` → `%s`; psycopg2 formats `%`. Neither may appear.
    assert "?" not in rk.REPOSITORY_HOST_PATTERN
    assert "%" not in rk.REPOSITORY_HOST_PATTERN
    re.compile(rk.REPOSITORY_HOST_PATTERN)


@pytest.mark.parametrize("work_type,url,source,expected", [
    ("article", "https://doi.org/10.1038/x", "OpenAlex fresh: AI", "article"),
    ("preprint", "https://doi.org/10.1101/x", "OpenAlex fresh: AI", "preprint"),
    ("review", "https://doi.org/10.1016/x", "OpenAlex: obesity", "review"),
    ("book-chapter", "https://link.springer.com/x", "OpenAlex: obesity", "chapter"),
    # non-paper types → artifact, whatever the host
    ("dataset", "https://doi.org/10.1234/x", "OpenAlex fresh: AI", "artifact"),
    ("software", "https://doi.org/10.1234/x", "OpenAlex fresh: AI", "artifact"),
    ("editorial", "https://doi.org/10.1234/x", "OpenAlex: obesity", "artifact"),
    ("letter", "https://doi.org/10.1234/x", "OpenAlex: obesity", "artifact"),
    # repository host wins over an admitted type (Zenodo deposits are typed article)
    ("article", "https://doi.org/10.5281/zenodo.22080387", "OpenAlex fresh: Computer vision", "artifact"),
    # no stored type: host net, then preprint servers, else unknown
    (None, "https://doi.org/10.5281/zenodo.1", "OpenAlex fresh: AI", "artifact"),
    (None, "https://arxiv.org/abs/2609.1", "arXiv Preprints", "preprint"),
    (None, "https://www.biorxiv.org/content/x", "biorxiv Preprints", "preprint"),
    (None, "https://www.nature.com/articles/x", "Nature", "unknown"),
    (None, "https://doi.org/10.1234/x", None, "unknown"),
])
def test_kind_for(work_type, url, source, expected):
    assert rk.kind_for(work_type, url, source) == expected
    assert expected in rk.KINDS


def test_kind_sql_mirrors_the_python_rules():
    sql = rk.kind_sql("m.work_type", "t.source_url", "t.source_name")
    assert sql.startswith("CASE WHEN t.source_url ~* '")
    assert rk.REPOSITORY_HOST_PATTERN in sql
    for t, k in rk.KIND_BY_TYPE.items():
        assert f"WHEN m.work_type = '{t}' THEN '{k}'" in sql
    assert "NOT IN ('article', 'book-chapter', 'preprint', 'review') THEN 'artifact'" in sql
    assert "t.source_name IN ('arXiv Preprints', 'biorxiv Preprints', 'medrxiv Preprints') THEN 'preprint'" in sql
    assert sql.endswith("ELSE 'unknown' END")
    assert "?" not in sql and "%" not in sql


def test_paper_filter_is_null_safe_and_aliasable():
    assert rk.paper_filter() == "coalesce(kind, 'unknown') <> 'artifact'"
    assert rk.paper_filter("rs.") == "coalesce(rs.kind, 'unknown') <> 'artifact'"
