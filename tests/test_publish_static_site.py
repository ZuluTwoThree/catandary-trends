"""publish_static_site.py — the incremental upload of the static export.

What must never happen: a write or delete outside REMOTE_ROOT/{trends,_next}
(the webroot holds the owner's landing page and the PHP double-opt-in with
its database password), a full re-upload after an aborted run, and an "empty"
export replacing the site after a database hiccup. Everything else is about
the order of operations, because shared hosting has no atomic swap.

The end-to-end tests run MODE=local against two temp directories; the SFTP
test starts a private OpenSSH sshd on a free localhost port (skipped where
sshd or sftp-server is not installed) — no network beyond 127.0.0.1.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import scripts.publish_static_site as ps

# ----------------------------------------------------------------------------
# fixtures / helpers
# ----------------------------------------------------------------------------
ARTICLE_FILES = {
    "trends/solar-glass-hits-grid-parity-101.html": "<html>a101</html>",
    "trends/solar-glass-hits-grid-parity-101.txt": "rsc a101",
    "trends/solar-glass-hits-grid-parity-101/__next._full.txt": "seg a101",
    "trends/postbiotic-snack-bars-202.html": "<html>a202</html>",
    "trends/postbiotic-snack-bars-202.txt": "rsc a202",
    "trends/postbiotic-snack-bars-202/__next._full.txt": "seg a202",
}
LISTING_FILES = {
    "trends/index.html": "<html>feed</html>",
    "trends/index.txt": "rsc feed",
    "trends/index.json": "[]",
    "trends/sitemap.xml": "<urlset/>",
    "trends/expired.html": "<html>gone</html>",
    "trends/mega/quantum-information-science.html": "<html>mega</html>",
    "trends/.htaccess": "RewriteEngine On",
}
ASSET_FILES = {
    "_next/static/chunks/main-abc123.js": "console.log(1)",
    "_next/static/css/app-def456.css": "body{}",
    "_next/.htaccess": "Header set Cache-Control immutable",
}
ROOT_FILES = {  # produced by the build but NOT managed by the publisher
    "index.html": "<html>export landing</html>",
    "404.html": "<html>404</html>",
    "sitemap.xml": "<urlset/>",
    ".htaccess": "root htaccess",
}
ROOT_MANAGED_FILES = {  # the ROOT_ALLOWLIST: feed page 1 as Next names it,
    "trends.html": "<html>feed page 1</html>",   # plus the generated robots.txt
    "trends.txt": "rsc feed page 1",             # and the TDM reservation file
    "robots.txt": "User-agent: GPTBot\nDisallow: /\n",
    ".well-known/tdmrep.json": '[{"location": "/*", "tdm-reservation": 1}]',
}
ALL_FILES = {**ARTICLE_FILES, **LISTING_FILES, **ASSET_FILES, **ROOT_FILES, **ROOT_MANAGED_FILES}
OWNER_FILES = {
    "index.html": "<html>OWNER landing</html>",
    "mark.svg": "<svg/>",
    "favicon.ico": "ico",
    "newsletter/subscribe.php": "<?php // db password inside",
    "newsletter/nl_config.php": "<?php $pw='secret';",
}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def make_export(tmp: Path, files: dict[str, str] | None = None, *, articles: int = 1500,
                built_at: datetime | None = None, name: str = "out") -> Path:
    """A fake build result: <name>/, <name>.manifest.tsv, <name>.build_info.json."""
    files = ALL_FILES if files is None else files
    out = tmp / name
    if out.exists():
        shutil.rmtree(out)
    write_tree(out, files)
    rows = sorted((rel, len(c.encode()), sha(c)) for rel, c in files.items())
    (tmp / f"{name}.manifest.tsv").write_text(
        "".join(f"{d}\t{n}\t{rel}\n" for rel, n, d in rows), encoding="utf-8")
    built = built_at or datetime.now().astimezone()
    (tmp / f"{name}.build_info.json").write_text(json.dumps({
        "built_at": built.isoformat(timespec="seconds"), "git_commit": "deadbeef",
        "articles": articles, "files": len(files), "bytes": sum(r[1] for r in rows),
        "window_days": 30, "noindex": True}), encoding="utf-8")
    return out


def write_config(path: Path, **kv) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{k}={v}\n" for k, v in kv.items()), encoding="utf-8")
    path.chmod(0o600)
    return path


def tree(root: Path) -> dict[str, str]:
    out = {}
    for p in root.rglob("*"):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    return out


@pytest.fixture
def site(tmp_path):
    """A fake export + a fake webspace with owner files and stale content."""
    out = make_export(tmp_path)
    dest = tmp_path / "webroot"
    write_tree(dest, OWNER_FILES)
    stale = {
        "trends/old-signal-9.html": "<html>old</html>",
        "trends/old-signal-9.txt": "rsc old",
        "trends/old-signal-9/__next._full.txt": "seg old",
        "trends/index.html": "<html>OLD feed</html>",
        "trends.html": "<html>OLD feed page 1</html>",
        "trends/.htaccess": "RewriteEngine On",
        "_next/static/chunks/main-old.js": "old js",
        "_next/static/css/app-def456.css": "body{}",
    }
    write_tree(dest, stale)
    remote_manifest = {rel: (sha(c), len(c.encode())) for rel, c in stale.items()}
    (dest / "trends" / ".publish-manifest.tsv").write_text(
        ps.format_manifest(remote_manifest), encoding="utf-8")
    cfg = write_config(tmp_path / "webspace.env", MODE="local", LOCAL_DEST=str(dest), CONNECTIONS=3)
    return {"tmp": tmp_path, "out": out, "dest": dest, "cfg": cfg, "stale": stale,
            "summary": tmp_path / "publish_last.json", "log": tmp_path / "publish.log"}


def run_main(site, *extra: str) -> int:
    return ps.main(["--config", str(site["cfg"]), "--out", str(site["out"]),
                    "--summary", str(site["summary"]), "--log-file", str(site["log"]),
                    "--no-lock", "--min-articles", "1", *extra])


# ----------------------------------------------------------------------------
# config
# ----------------------------------------------------------------------------
class TestConfig:
    def test_missing_file_is_refused_with_a_hint(self, tmp_path):
        with pytest.raises(ps.Refused, match="webspace config missing"):
            ps.load_config(tmp_path / "nope.env")

    def test_group_or_world_readable_file_is_refused(self, tmp_path):
        p = write_config(tmp_path / "w.env", MODE="local", LOCAL_DEST="/x")
        p.chmod(0o640)
        with pytest.raises(ps.Refused, match="0600"):
            ps.load_config(p)

    def test_values_quotes_comments_and_export_prefix(self, tmp_path):
        p = tmp_path / "w.env"
        p.write_text('# comment\nexport MODE="sftp"\nHOST=host.example  # trailing\n'
                     "USER='u'\nPASSWORD='p#ss w0rd'\nREMOTE_ROOT=/public_html\nPORT=2222\n"
                     "CONNECTIONS=9\n")
        p.chmod(0o600)
        cfg = ps.load_config(p)
        assert (cfg.mode, cfg.host, cfg.user, cfg.password) == ("sftp", "host.example", "u", "p#ss w0rd")
        assert cfg.port == 2222 and cfg.remote_root == "/public_html"
        assert cfg.connections == 4, "sftp sessions are capped at 4 — shared hosting"

    @pytest.mark.parametrize("kv,msg", [
        ({"MODE": "ftp"}, "MODE must be"),
        ({"MODE": "sftp", "HOST": "h", "USER": "u", "REMOTE_ROOT": "/r"}, "PASSWORD or KEY_FILE"),
        ({"MODE": "sftp", "HOST": "h", "USER": "u", "PASSWORD": "p"}, "REMOTE_ROOT"),
        ({"MODE": "local"}, "LOCAL_DEST"),
    ])
    def test_incomplete_config_is_refused(self, tmp_path, kv, msg):
        p = write_config(tmp_path / "w.env", **kv)
        with pytest.raises(ps.Refused, match=msg):
            ps.load_config(p)


# ----------------------------------------------------------------------------
# paths — the owner's webroot is sacred
# ----------------------------------------------------------------------------
class TestPaths:
    @pytest.mark.parametrize("bad", ["../index.html", "trends/../index.html", "/etc/passwd",
                                     "trends/..", "..", "trends\\x.html", "~/x", "",
                                     "trends/a/../../newsletter/x.php"])
    def test_traversal_and_absolute_paths_are_violations(self, bad):
        with pytest.raises(ps.PathViolation):
            ps.normalize_rel(bad)

    def test_normalisation_keeps_managed_paths_clean(self):
        assert ps.normalize_rel("./trends//a-1.html") == "trends/a-1.html"
        assert ps.normalize_rel("_next/static/x.js") == "_next/static/x.js"

    @pytest.mark.parametrize("rel", ["index.html", "mark.svg", "favicon.ico",
                                     "newsletter/subscribe.php", "sitemap.xml", "imprint.html",
                                     "trendsx/a.html", "404.html", ".htaccess", "trends.htm",
                                     "Trends.html", "trendsx.html", "x/trends.html",
                                     "trends.html/x", "trends.json", ".publish-manifest.tsv"])
    def test_owner_and_root_files_are_never_managed(self, rel):
        assert not ps.is_managed(rel)
        with pytest.raises(ps.PathViolation):
            ps.guard_remote("/public_html", rel)

    @pytest.mark.parametrize("rel", ["trends/clients", "trends/clients/.htaccess",
                                     "trends/clients/acme/2026-W38.pdf"])
    def test_customer_areas_are_owner_subtrees(self, rel):
        """trends/clients/<kunde>/ (Field Watch, 2026-09-20) is uploaded by hand
        and lives INSIDE the managed prefix: never written, never listed, never
        deleted — the sftp plan drops it, --full skips it, rsync excludes it."""
        assert not ps.is_managed(rel)
        with pytest.raises(ps.PathViolation):
            ps.guard_remote("/public_html", rel)
        remote = {rel: (None, 10), "trends/a-1.html": ("x", 1)}
        plan = ps.build_plan({"trends/a-1.html": ("x", 1)}, remote)
        assert plan.deletes == []
        assert ps.rsync_owner_excludes("trends") == ["--exclude", "/clients/"]
        assert ps.rsync_owner_excludes("_next") == []

    def test_root_allowlist_is_exactly_feed_page_one(self):
        """trends.html + trends.txt are the only webroot files the publisher
        owns (Next writes /trends there; /trends.txt is the router's payload)."""
        assert ps.ROOT_ALLOWLIST == {"trends.html", "trends.txt", "robots.txt", ".well-known/tdmrep.json"}
        assert not (ps.ROOT_ALLOWLIST & ps.OWNER_PROTECTED)
        for rel in sorted(ps.ROOT_ALLOWLIST):
            assert ps.is_managed(rel)
            assert ps.guard_remote("/public_html", rel) == f"/public_html/{rel}"
            # the atomic put+rename twin is reachable, nothing else at the root is
            assert ps.guard_remote("/public_html", rel + ps.TMP_SUFFIX) == f"/public_html/{rel}{ps.TMP_SUFFIX}"
            assert ps.phase_of(rel) == "listing"
        with pytest.raises(ps.PathViolation):
            ps.guard_remote("/public_html", "index.html" + ps.TMP_SUFFIX)

    def test_guard_resolves_inside_the_subtrees_only(self):
        assert ps.guard_remote("/public_html", "trends/a-1.html") == "/public_html/trends/a-1.html"
        assert ps.guard_remote("/public_html/", "_next/.htaccess") == "/public_html/_next/.htaccess"
        assert ps.guard_remote("/public_html", "trends") == "/public_html/trends"
        assert ps.guard_remote("public_html", "trends/x") == "public_html/trends/x"

    def test_managed_prefixes_cannot_be_pointed_at_owner_files(self):
        for bad in (("newsletter",), ("trends", "index.html"), (".",), ("",), ("a/b",)):
            with pytest.raises(ps.Refused):
                ps.validate_managed(bad)

    def test_a_backend_refuses_owner_paths_even_when_asked_directly(self, tmp_path):
        cfg = ps.Config(mode="local", local_dest=str(tmp_path), remote_root=str(tmp_path))
        b = ps.LocalBackend(cfg, ps.MANAGED_PREFIXES)
        b.connect()
        for rel in ("index.html", "newsletter/x.php", "trends/../index.html"):
            with pytest.raises(ps.PathViolation):
                b.put_text("x", rel)
            with pytest.raises(ps.PathViolation):
                b.remove(rel)
        assert not (tmp_path / "index.html").exists()


# ----------------------------------------------------------------------------
# manifest diff + ordering
# ----------------------------------------------------------------------------
class TestManifestDiff:
    def test_new_changed_deleted_unchanged(self):
        local = {"trends/a-1.html": ("aa", 10), "trends/b-2.html": ("bb2", 12),
                 "trends/c-3.html": ("cc", 5), "index.html": ("root", 1)}
        remote = {"trends/a-1.html": ("aa", 10), "trends/b-2.html": ("bb", 11),
                  "trends/z-9.html": ("zz", 3), "index.html": ("OWNER", 99)}
        plan = ps.build_plan(local, remote)
        assert {i.path: i.reason for i in plan.uploads} == {"trends/b-2.html": "changed",
                                                            "trends/c-3.html": "new"}
        assert plan.deletes == ["trends/z-9.html"]
        assert plan.unchanged == 1
        assert plan.outside_scope == 1, "root index.html from the build is skipped, not uploaded"
        assert plan.remote_total == 3, "the owner's index.html in a stray remote manifest is not counted"

    def test_root_allowlist_travels_and_is_deleted_only_by_name(self):
        local = {"trends.html": ("h1", 10), "trends.txt": ("t1", 4), "trends/a-1.html": ("a", 1),
                 "index.html": ("root", 1), "404.html": ("nf", 1)}
        remote = {"trends.html": ("h0", 9), "index.html": ("OWNER", 99), "imprint.html": ("x", 1),
                  "trends.txt": ("t1", 4)}
        plan = ps.build_plan(local, remote)
        assert {i.path: i.reason for i in plan.uploads} == {"trends.html": "changed",
                                                            "trends/a-1.html": "new"}
        assert plan.unchanged == 1 and plan.outside_scope == 2
        assert plan.deletes == []
        # a root file the build no longer produces goes — but only an allowlisted one
        plan = ps.build_plan({"trends/a-1.html": ("a", 1)}, remote)
        assert plan.deletes == ["trends.html", "trends.txt"]

    def test_remote_only_owner_entries_are_never_deleted(self):
        remote = {"index.html": ("x", 1), "newsletter/subscribe.php": ("y", 2),
                  "robots.txt": ("z", 3), "trends/a-1.html": ("a", 4)}
        plan = ps.build_plan({}, remote)
        # robots.txt is export-managed since 2026-09-03: gone when the build stops producing it
        assert plan.deletes == ["robots.txt", "trends/a-1.html"]

    def test_traversal_in_local_manifest_aborts(self):
        with pytest.raises(ps.PathViolation):
            ps.build_plan({"trends/../newsletter/x.php": ("a", 1)}, {})

    def test_traversal_in_remote_data_is_dropped_not_fatal(self):
        plan = ps.build_plan({"trends/a-1.html": ("a", 1)}, {"trends/../index.html": ("b", 2)})
        assert plan.deletes == [] and len(plan.uploads) == 1

    def test_unknown_remote_hash_falls_back_to_size(self):
        """--full lists the remote (path+size only): same size = assumed equal."""
        local = {"trends/a-1.html": ("aa", 10), "trends/b-2.html": ("bb", 12)}
        remote = {"trends/a-1.html": (None, 10), "trends/b-2.html": (None, 11)}
        plan = ps.build_plan(local, remote)
        assert [i.path for i in plan.uploads] == ["trends/b-2.html"]
        assert plan.assumed_unchanged == 1

    def test_manifest_round_trip(self):
        entries = {"trends/a-1.html": ("aa", 10), "_next/x.js": (None, 3)}
        assert ps.parse_manifest(ps.format_manifest(entries)) == entries
        with pytest.raises(ps.Refused):
            ps.parse_manifest("only\ttwo\n")


class TestOrder:
    def test_phases_assets_articles_listing_with_htaccess_last(self):
        local = {rel: (sha(c), len(c)) for rel, c in ALL_FILES.items()}
        plan = ps.build_plan(local, {})
        paths = [i.path for i in plan.uploads]
        phases = [i.phase for i in plan.uploads]
        # phases are contiguous and in order
        assert phases == sorted(phases, key=ps.PHASES.index)
        assert phases[0] == "assets" and phases[-1] == "listing"
        # .htaccess files come after everything else, sitemap after listing pages
        assert paths[-2:] == ["_next/.htaccess", "trends/.htaccess"]
        assert paths.index("trends/sitemap.xml") > paths.index("trends/index.html")
        assert paths.index("trends/sitemap.xml") > paths.index("trends/mega/quantum-information-science.html")
        # article payloads belong to the article phase, mega/expired/index to listing
        for rel in ARTICLE_FILES:
            assert ps.phase_of(rel) == "articles", rel
        for rel in ("trends/mega/quantum-information-science.html", "trends/expired.html",
                    "trends/index.json", "trends/page/2.html", "trends/v/tech.html",
                    "trends/index.html", "trends.html", "trends.txt"):
            assert ps.phase_of(rel) == "listing", rel
        assert ps.phase_of("_next/static/chunks/x.js") == "assets"


# ----------------------------------------------------------------------------
# gates
# ----------------------------------------------------------------------------
class TestGates:
    NOW = datetime(2026, 9, 3, 6, 30, tzinfo=timezone(timedelta(hours=2)))

    def info(self, hours_old=1.0, articles=15000):
        return {"built_at": (self.NOW - timedelta(hours=hours_old)).isoformat(), "articles": articles}

    def test_fresh_and_full_passes(self):
        ps.check_build(self.info(), 15000, min_articles=1000, max_age_hours=12, now=self.NOW)

    def test_stale_build_is_refused(self):
        with pytest.raises(ps.Refused, match="stale"):
            ps.check_build(self.info(hours_old=13), 15000, min_articles=1000, max_age_hours=12, now=self.NOW)

    def test_empty_export_is_refused(self):
        with pytest.raises(ps.Refused, match="only 12 articles"):
            ps.check_build(self.info(articles=12), 12, min_articles=1000, max_age_hours=12, now=self.NOW)

    def test_manifest_article_count_is_checked_independently(self):
        """build_info says 15k but the manifest has no article pages under
        trends/ — the export layout moved and the publisher must not delete
        the live articles on the strength of a stale build_info."""
        with pytest.raises(ps.Refused, match="layout changed"):
            ps.check_build(self.info(), 0, min_articles=1000, max_age_hours=12, now=self.NOW)

    def test_missing_build_info_is_refused(self, tmp_path):
        with pytest.raises(ps.Refused, match="build info missing"):
            ps.read_build_info(tmp_path / "out")

    def test_mass_deletion_needs_force(self, site):
        """Remote holds 7 managed files, the new export keeps only one of
        them (the css) — 6/7 deleted is above 60 % and refused."""
        make_export(site["tmp"], {"_next/static/css/app-def456.css": "body{}",
                                  "trends/only-one-3.html": "x", **ROOT_FILES})
        rc = run_main(site, "--apply")
        assert rc == ps.EXIT_REFUSED
        assert (site["dest"] / "trends/old-signal-9.html").exists(), "nothing was deleted"
        assert json.loads(site["summary"].read_text())["status"] == "refused"
        rc = run_main(site, "--apply", "--force")
        assert rc == ps.EXIT_OK
        assert not (site["dest"] / "trends/old-signal-9.html").exists()

    def test_min_articles_gate_via_cli(self, site):
        rc = run_main(site, "--apply", "--min-articles", "5000")
        assert rc == ps.EXIT_REFUSED
        assert (site["dest"] / "trends/old-signal-9.html").exists()

    def test_missing_config_exits_2(self, site, tmp_path):
        rc = ps.main(["--config", str(tmp_path / "none.env"), "--out", str(site["out"]),
                      "--summary", str(site["summary"]), "--log-file", "-", "--no-lock"])
        assert rc == ps.EXIT_REFUSED


# ----------------------------------------------------------------------------
# end-to-end, MODE=local
# ----------------------------------------------------------------------------
class TestLocalEndToEnd:
    def test_dry_run_is_the_default_and_touches_nothing(self, site, capsys):
        before = tree(site["dest"])
        rc = run_main(site)
        assert rc == ps.EXIT_OK
        assert tree(site["dest"]) == before
        assert not site["summary"].exists(), "a dry-run must not satisfy the watchdog"
        out = capsys.readouterr().out
        assert "assets" in out and "articles" in out and "listing" in out and "delete" in out
        assert "outside scope" in out

    def test_apply_syncs_managed_subtrees_and_leaves_the_owner_alone(self, site):
        rc = run_main(site, "--apply")
        assert rc == ps.EXIT_OK
        got = tree(site["dest"])
        # owner files byte-identical, never overwritten by the export's own root files
        for rel, content in OWNER_FILES.items():
            assert got[rel] == content, rel
        assert "404.html" not in got and ".htaccess" not in got and "sitemap.xml" not in got
        # the two allowlisted root files did travel (stale trends.html replaced)
        for rel, content in ROOT_MANAGED_FILES.items():
            assert got[rel] == content, rel
        # managed content = the export's managed files, stale ones gone
        managed_local = {r: c for r, c in ALL_FILES.items() if ps.is_managed(r)}
        managed_remote = {r: c for r, c in got.items() if ps.is_managed(r) and r != ps.REMOTE_MANIFEST}
        assert managed_remote == managed_local
        assert not (site["dest"] / "trends/old-signal-9").exists(), "empty article dir removed"
        # manifest mirrors the managed set
        remote_manifest = ps.parse_manifest(got[ps.REMOTE_MANIFEST])
        assert set(remote_manifest) == set(managed_local)
        assert all(remote_manifest[r][0] == sha(c) for r, c in managed_local.items())
        # no temp files left behind
        assert not [r for r in got if r.endswith(ps.TMP_SUFFIX)]
        # summary for the watchdog
        s = json.loads(site["summary"].read_text())
        assert s["status"] == "ok" and s["errors"] == 0 and s["dry_run"] is False
        assert s["uploaded"] == len(managed_local) - 2        # css + trends/.htaccess unchanged
        assert s["deleted"] == 4                             # old-9 (3 files) + main-old.js
        assert s["unchanged"] == 2
        assert s["skipped_outside_scope"] == len(ROOT_FILES)
        assert s["finished_at"].startswith(datetime.now().strftime("%Y-%m-%d"))
        assert site["log"].exists() and "done: status=ok" in site["log"].read_text()

    def test_full_mode_stats_root_files_and_never_lists_the_webroot(self, site):
        assert run_main(site, "--apply") == ps.EXIT_OK
        (site["dest"] / ps.REMOTE_MANIFEST).unlink()          # lost manifest → --full
        (site["dest"] / "trends" / "stray-777.html").write_text("stray")
        (site["dest"] / "foreign.html").write_text("someone else's root file")
        assert run_main(site, "--apply", "--full") == ps.EXIT_OK
        got = tree(site["dest"])
        assert "trends/stray-777.html" not in got
        assert got["foreign.html"] == "someone else's root file"
        for rel, content in OWNER_FILES.items():
            assert got[rel] == content, rel
        for rel, content in ROOT_MANAGED_FILES.items():
            assert got[rel] == content, rel
        s = json.loads(site["summary"].read_text())
        assert s["status"] == "ok" and s["uploaded"] == 0 and s["deleted"] == 1
        # the rebuilt manifest knows the root files again (size-matched → hash unknown → '-')
        remote_manifest = ps.parse_manifest(got[ps.REMOTE_MANIFEST])
        assert set(ROOT_MANAGED_FILES) <= set(remote_manifest)

    def test_second_run_is_a_no_op(self, site):
        assert run_main(site, "--apply") == ps.EXIT_OK
        before = tree(site["dest"])
        assert run_main(site, "--apply") == ps.EXIT_OK
        assert tree(site["dest"]) == before
        s = json.loads(site["summary"].read_text())
        assert s["uploaded"] == 0 and s["deleted"] == 0 and s["status"] == "ok"

    def test_only_the_changed_file_travels(self, site):
        assert run_main(site, "--apply") == ps.EXIT_OK
        files = dict(ALL_FILES)
        files["trends/index.html"] = "<html>feed v2</html>"
        files["trends/new-article-303.html"] = "<html>303</html>"
        del files["trends/postbiotic-snack-bars-202.html"]
        make_export(site["tmp"], files)
        assert run_main(site, "--apply") == ps.EXIT_OK
        s = json.loads(site["summary"].read_text())
        assert s["uploaded"] == 2 and s["deleted"] == 1
        got = tree(site["dest"])
        assert got["trends/index.html"] == "<html>feed v2</html>"
        assert "trends/postbiotic-snack-bars-202.html" not in got
        assert got["trends/postbiotic-snack-bars-202.txt"] == "rsc a202"

    def test_aborted_run_resumes_from_the_checkpoint(self, site, monkeypatch):
        """Break the upload of one article page. The assets phase completed,
        the listing phase must NOT run (its pages would link to a missing
        article), the deletion must not run either, and the checkpointed
        manifest lets the next run finish with only the remaining files."""
        victim = "trends/postbiotic-snack-bars-202.html"
        real_put = ps.LocalBackend._put

        def flaky_put(self, local, absdst):
            if absdst.endswith(victim + ps.TMP_SUFFIX):
                raise OSError("simulated connection reset")
            return real_put(self, local, absdst)

        monkeypatch.setattr(ps.LocalBackend, "_put", flaky_put)
        rc = run_main(site, "--apply", "--checkpoint-every", "2")
        assert rc == ps.EXIT_ERROR
        got = tree(site["dest"])
        assert "_next/static/chunks/main-abc123.js" in got          # phase (a) done
        assert "trends/sitemap.xml" not in got                       # phase (c) skipped
        assert got["trends/index.html"] == "<html>OLD feed</html>"   # listing untouched
        assert "trends/old-signal-9.html" in got                     # deletion skipped
        s = json.loads(site["summary"].read_text())
        assert s["status"] == "error" and s["errors"] == 1
        assert "simulated" in s["error_samples"][0]
        checkpoint = ps.parse_manifest(got[ps.REMOTE_MANIFEST])
        assert "_next/static/chunks/main-abc123.js" in checkpoint
        assert victim not in checkpoint

        monkeypatch.setattr(ps.LocalBackend, "_put", real_put)
        rc = run_main(site, "--apply")
        assert rc == ps.EXIT_OK
        s = json.loads(site["summary"].read_text())
        managed_local = {r for r in ALL_FILES if ps.is_managed(r)}
        assert s["uploaded"] < len(managed_local), "resume, not a full re-upload"
        assert s["resumed"] is True
        got = tree(site["dest"])
        assert got[victim] == ALL_FILES[victim]
        assert "trends/old-signal-9.html" not in got

    def test_full_mode_uses_the_listing_and_removes_strays(self, site):
        assert run_main(site, "--apply") == ps.EXIT_OK
        stray = site["dest"] / "trends" / "manually-uploaded-777.html"
        stray.write_text("stray")
        leftover = site["dest"] / "trends" / ("x" + ps.TMP_SUFFIX)
        leftover.write_text("half")
        assert run_main(site, "--apply") == ps.EXIT_OK
        assert stray.exists(), "manifest mode does not know about the stray file"
        assert run_main(site, "--apply", "--full") == ps.EXIT_OK
        assert not stray.exists() and not leftover.exists()
        got = tree(site["dest"])
        for rel, content in OWNER_FILES.items():
            assert got[rel] == content

    def test_first_run_without_remote_manifest(self, site):
        (site["dest"] / "trends" / ".publish-manifest.tsv").unlink()
        assert run_main(site, "--apply") == ps.EXIT_OK
        got = tree(site["dest"])
        assert "trends/old-signal-9.html" in got, "without a manifest nothing is deleted (use --full)"
        assert got["trends/index.html"] == ALL_FILES["trends/index.html"]
        assert json.loads(site["summary"].read_text())["resumed"] is False

    def test_zero_managed_files_is_refused(self, site):
        make_export(site["tmp"], dict(ROOT_FILES))
        assert run_main(site, "--apply") == ps.EXIT_REFUSED
        assert (site["dest"] / "trends/old-signal-9.html").exists()


# ----------------------------------------------------------------------------
# MODE=rsync against a local directory (no ssh involved)
# ----------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync not installed")
class TestRsyncLocal:
    def test_command_shape(self, tmp_path):
        cfg = ps.Config(mode="rsync", host="wp1.example", user="u", port=222,
                        key_file="/k", remote_root="/public_html")
        cmd = ps.build_rsync_cmd(cfg, tmp_path / "out", "trends", dry_run=True)
        assert cmd[0] == "rsync" and "--delete" in cmd and "--delay-updates" in cmd and "-n" in cmd
        assert cmd[-1] == "u@wp1.example:/public_html/trends/"
        assert cmd[-2] == str(tmp_path / "out" / "trends") + "/"
        assert cmd[cmd.index("-e") + 1] == "ssh -p 222 -o BatchMode=yes -i /k"
        assert ".publish-manifest.tsv" in cmd
        with pytest.raises(ps.PathViolation):
            ps.rsync_target(cfg, "newsletter")

    def test_itemize_parser(self):
        out = (">f+++++++++ 120 trends/a-1.html\n>f.st...... 99 trends/index.html\n"
               ".f..t...... 5 trends/same.html\ncd+++++++++ 0 trends/a-1/\n*deleting   trends/old-9.html\n")
        assert ps.parse_rsync_itemize(out) == {"new": 1, "changed": 1, "deleted": 1, "bytes": 219}

    def test_rsync_end_to_end(self, site):
        write_config(site["cfg"], MODE="rsync", REMOTE_ROOT=str(site["dest"]))
        rc = run_main(site)
        assert rc == ps.EXIT_OK and not site["summary"].exists()
        rc = run_main(site, "--apply")
        assert rc == ps.EXIT_OK
        got = tree(site["dest"])
        for rel, content in OWNER_FILES.items():
            assert got[rel] == content
        managed_local = {r: c for r, c in ALL_FILES.items() if ps.is_managed(r)}
        managed_remote = {r: c for r, c in got.items() if ps.is_managed(r) and r != ps.REMOTE_MANIFEST}
        assert managed_remote == managed_local
        assert set(ps.parse_manifest(got[ps.REMOTE_MANIFEST])) == set(managed_local)
        s = json.loads(site["summary"].read_text())
        assert s["status"] == "ok" and s["errors"] == 0 and s["deleted"] == 4


# ----------------------------------------------------------------------------
# MODE=sftp against a private sshd on localhost
# ----------------------------------------------------------------------------
SSHD = shutil.which("sshd") or "/usr/sbin/sshd"
SFTP_SERVER = next((p for p in ("/usr/lib/openssh/sftp-server", "/usr/libexec/openssh/sftp-server",
                                "/usr/lib/ssh/sftp-server") if os.path.exists(p)), None)
paramiko = pytest.importorskip("paramiko", reason="paramiko not installed") if False else None
try:
    import paramiko  # noqa: F401,F811
    HAVE_PARAMIKO = True
except ImportError:
    HAVE_PARAMIKO = False


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def local_sshd(tmp_path_factory):
    if not (os.path.exists(SSHD) and SFTP_SERVER and HAVE_PARAMIKO and shutil.which("ssh-keygen")):
        pytest.skip("needs sshd + sftp-server + ssh-keygen + paramiko")
    d = tmp_path_factory.mktemp("sshd")
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(d / "hostkey")], check=True)
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(d / "clientkey")], check=True)
    port = free_port()
    (d / "sshd_config").write_text(f"""Port {port}
ListenAddress 127.0.0.1
HostKey {d}/hostkey
PidFile {d}/sshd.pid
AuthorizedKeysFile {d}/clientkey.pub
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
UsePAM no
StrictModes no
LogLevel ERROR
Subsystem sftp {SFTP_SERVER}
""")
    proc = subprocess.Popen([SSHD, "-f", str(d / "sshd_config"), "-D", "-e"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 10
    up = False
    while time.time() < deadline and proc.poll() is None:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                up = True
                break
        except OSError:
            time.sleep(0.2)
    if not up:
        proc.kill()
        pytest.skip("local sshd did not come up (sandbox?)")
    yield {"port": port, "key": str(d / "clientkey"), "dir": d,
           "user": os.environ.get("USER") or os.getlogin()}
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


class TestSftpEndToEnd:
    def test_sftp_publish_resume_and_full(self, site, local_sshd):
        write_config(site["cfg"], MODE="sftp", HOST="127.0.0.1", PORT=local_sshd["port"],
                     USER=local_sshd["user"], KEY_FILE=local_sshd["key"],
                     REMOTE_ROOT=str(site["dest"]), CONNECTIONS=3,
                     HOST_KEY_POLICY="accept-new", KNOWN_HOSTS=str(site["tmp"] / "known_hosts"))
        # dry-run reads the remote manifest over sftp, writes nothing
        before = tree(site["dest"])
        assert run_main(site) == ps.EXIT_OK
        assert tree(site["dest"]) == before
        # apply: three parallel sessions, atomic put+rename, deletes last
        assert run_main(site, "--apply", "--checkpoint-every", "3") == ps.EXIT_OK
        got = tree(site["dest"])
        for rel, content in OWNER_FILES.items():
            assert got[rel] == content
        managed_local = {r: c for r, c in ALL_FILES.items() if ps.is_managed(r)}
        managed_remote = {r: c for r, c in got.items() if ps.is_managed(r) and r != ps.REMOTE_MANIFEST}
        assert managed_remote == managed_local
        assert not (site["dest"] / "trends/old-signal-9").exists()
        assert not [r for r in got if r.endswith(ps.TMP_SUFFIX)]
        s = json.loads(site["summary"].read_text())
        assert s["mode"] == "sftp" and s["status"] == "ok" and s["deleted"] == 4
        assert (site["tmp"] / "known_hosts").read_text().strip(), "accept-new saved the host key"
        # strict policy now succeeds because the key is known
        write_config(site["cfg"], MODE="sftp", HOST="127.0.0.1", PORT=local_sshd["port"],
                     USER=local_sshd["user"], KEY_FILE=local_sshd["key"],
                     REMOTE_ROOT=str(site["dest"]), CONNECTIONS=2,
                     HOST_KEY_POLICY="strict", KNOWN_HOSTS=str(site["tmp"] / "known_hosts"))
        stray = site["dest"] / "trends" / "manually-uploaded-777.html"
        stray.write_text("stray")
        assert run_main(site, "--apply", "--full") == ps.EXIT_OK
        assert not stray.exists()
        s = json.loads(site["summary"].read_text())
        assert s["status"] == "ok" and s["uploaded"] == 0 and s["deleted"] == 1

    def test_unknown_host_key_is_rejected_under_strict(self, site, local_sshd):
        write_config(site["cfg"], MODE="sftp", HOST="127.0.0.1", PORT=local_sshd["port"],
                     USER=local_sshd["user"], KEY_FILE=local_sshd["key"],
                     REMOTE_ROOT=str(site["dest"]), HOST_KEY_POLICY="strict",
                     KNOWN_HOSTS=str(site["tmp"] / "empty_known_hosts"))
        rc = run_main(site, "--apply")
        assert rc == ps.EXIT_ERROR
        assert (site["dest"] / "trends/old-signal-9.html").exists()


# ----------------------------------------------------------------------------
# watchdog integration
# ----------------------------------------------------------------------------
@pytest.fixture
def wd(tmp_path, monkeypatch):
    import scripts.cycle_watchdog as m
    m = importlib.reload(m)
    monkeypatch.setattr(m, "LOG_DIR", tmp_path)
    monkeypatch.setattr(m, "PUBLISH_CONFIG", tmp_path / "webspace.env")
    monkeypatch.setattr(m, "PUBLISH_LAST", tmp_path / "publish_last.json")
    monkeypatch.setattr(m, "publish_is_running", lambda: False)
    return m


class TestWatchdogPublish:
    STAMP = "20260903"

    def summary(self, wd, **kv):
        base = {"finished_at": "2026-09-03T06:41:12+02:00", "status": "ok", "errors": 0,
                "uploaded": 1234, "deleted": 590}
        base.update(kv)
        wd.PUBLISH_LAST.write_text(json.dumps(base))

    def test_dormant_without_webspace_config(self, wd):
        v = wd.inspect_publish(self.STAMP)
        assert v["ok"] is True and v["kind"] == "publish-unconfigured"

    def test_clean_run_today_is_silent(self, wd):
        wd.PUBLISH_CONFIG.write_text("MODE=sftp\n")
        self.summary(wd)
        v = wd.inspect_publish(self.STAMP)
        assert v["ok"] is True and "1234" in v["headline"]

    def test_never_published_is_reported_once_configured(self, wd):
        wd.PUBLISH_CONFIG.write_text("MODE=sftp\n")
        v = wd.inspect_publish(self.STAMP)
        assert v["ok"] is False and v["kind"] == "publish-missing"
        assert "publish_static_site" in v["detail"]

    def test_yesterdays_summary_is_stale(self, wd):
        wd.PUBLISH_CONFIG.write_text("MODE=sftp\n")
        self.summary(wd, finished_at="2026-09-02T06:41:12+02:00")
        v = wd.inspect_publish(self.STAMP)
        assert v["ok"] is False and v["kind"] == "publish-stale"

    def test_errors_today_are_a_failure(self, wd):
        wd.PUBLISH_CONFIG.write_text("MODE=sftp\n")
        self.summary(wd, status="error", errors=3, error_samples=["upload trends/x-1.html: EOF"])
        v = wd.inspect_publish(self.STAMP)
        assert v["ok"] is False and v["kind"] == "publish-failed"
        assert "trends/x-1.html" in v["detail"] and "resumes" in v["detail"]

    def test_still_running_is_not_called_stale(self, wd, monkeypatch):
        wd.PUBLISH_CONFIG.write_text("MODE=sftp\n")
        self.summary(wd, finished_at="2026-09-02T06:41:12+02:00")
        monkeypatch.setattr(wd, "publish_is_running", lambda: True)
        v = wd.inspect_publish(self.STAMP)
        assert v["kind"] == "publish-running"

    def test_mail_carries_the_publish_log_tail(self, wd, tmp_path):
        wd.PUBLISH_CONFIG.write_text("MODE=sftp\n")
        self.summary(wd, status="error", errors=1)
        (tmp_path / f"catandary-publish-{self.STAMP}.log").write_text("line one\nphase assets: 5/5\n")
        subject, body_html, text = wd.build_mail(wd.inspect_publish(self.STAMP), self.STAMP)
        assert "03.09.2026" in subject and "publish failed" in subject
        assert "phase assets: 5/5" in text and "phase assets: 5/5" in body_html
