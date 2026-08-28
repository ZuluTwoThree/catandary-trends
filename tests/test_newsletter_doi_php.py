"""Trusted-proxy IP resolution for the Hetzner DOI newsletter flow (#16/#82).

`docs/launch/newsletter-doi-php/` is a repo-tracked mirror of the PHP files that
run on the (non-Python) Hetzner shared-hosting webspace — there is no PHP
runtime in this project's normal dev/CI environment. These tests run the REAL
`_lib.php` (via `php -l` and via `php` subprocess execution, `require`d
unmodified — no regex/eval extraction) whenever a `php` CLI happens to be on
PATH, and skip cleanly otherwise. Locally, a PHP 8.2 sandbox is available via:

    docker run --rm -v "$PWD/docs/launch/newsletter-doi-php":/app -w /app \\
        php:8.2-cli php -l _lib.php

`nl_client_ip()` decides which IP is trusted as the source of X-Forwarded-For.
`NL_TRUSTED_PROXIES` (nl_config.php, empty by default) is the #16 patch that
lets a VPS reverse-proxy (#82/#93, public IP) be trusted in addition to the
pre-existing private/loopback (Varnish) case — getting this wrong makes the
DSGVO Art. 7 consent-IP evidence worthless and collapses the IP rate limit
into one shared bucket. See docs/launch/newsletter-doi-php/EINBAU.md
("Naechster Upload") and NEWSLETTER_GOLIVE.md.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

PHP_BIN = shutil.which("php")
pytestmark = pytest.mark.skipif(PHP_BIN is None, reason="no php CLI on PATH")

DOI_DIR = Path(__file__).resolve().parent.parent / "docs" / "launch" / "newsletter-doi-php"
LIB_PHP = DOI_DIR / "_lib.php"

# runner.php requires the REAL _lib.php unmodified and calls nl_client_ip()
# with $_SERVER populated from the env vars this test sets — no eval/regex
# extraction of the function body, so the test tracks the shipped file exactly.
RUNNER_PHP = textwrap.dedent(
    """\
    <?php
    declare(strict_types=1);
    $_SERVER['REMOTE_ADDR'] = getenv('NL_TEST_REMOTE') ?: '0.0.0.0';
    $xff = getenv('NL_TEST_XFF');
    if ($xff !== false && $xff !== '') {
        $_SERVER['HTTP_X_FORWARDED_FOR'] = $xff;
    }
    require __DIR__ . '/_lib.php';
    echo nl_client_ip();
    """
)

# Minimal stand-in for the real (secret-bearing, git-ignored) nl_config.php.
# NL_TEST_TRUSTED is a JSON array of trusted proxy IPs (possibly empty).
CONFIG_PHP_TEMPLATE = textwrap.dedent(
    """\
    <?php
    define('NL_TRUSTED_PROXIES', json_decode(getenv('NL_TEST_TRUSTED') ?: '[]', true));
    return ['app_secret' => 'test-only'];
    """
)


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory) -> Path:
    """A temp dir with the real _lib.php plus a throwaway nl_config.php/runner.php."""
    d = tmp_path_factory.mktemp("nl_doi_sandbox")
    (d / "_lib.php").write_text(LIB_PHP.read_text(encoding="utf-8"), encoding="utf-8")
    (d / "nl_config.php").write_text(CONFIG_PHP_TEMPLATE, encoding="utf-8")
    (d / "runner.php").write_text(RUNNER_PHP, encoding="utf-8")
    return d


def _client_ip(sandbox: Path, remote: str, xff: str, trusted: list[str]) -> str:
    env = {
        "NL_TEST_REMOTE": remote,
        "NL_TEST_XFF": xff,
        "NL_TEST_TRUSTED": json.dumps(trusted),
        "PATH": "/usr/bin:/bin",
    }
    proc = subprocess.run(
        [PHP_BIN, str(sandbox / "runner.php")],
        capture_output=True, text=True, env=env, timeout=10, check=True,
    )
    assert proc.stderr == "", f"php stderr: {proc.stderr}"
    return proc.stdout


def test_php_lint_all_doi_files():
    """Every shipped PHP file in the repo-tracked webspace mirror parses cleanly."""
    php_files = sorted(DOI_DIR.glob("*.php"))
    assert php_files, "expected .php files under docs/launch/newsletter-doi-php/"
    for f in php_files:
        proc = subprocess.run(
            [PHP_BIN, "-l", str(f)], capture_output=True, text=True, timeout=10,
        )
        assert proc.returncode == 0, f"{f.name}: {proc.stdout}{proc.stderr}"


def test_empty_trusted_list_matches_legacy_varnish_behavior(sandbox):
    """NL_TRUSTED_PROXIES == [] (the default) must reproduce the pre-#16 logic:

    private/loopback REMOTE_ADDR (Varnish) -> take the rightmost valid,
    non-private XFF entry.
    """
    got = _client_ip(sandbox, "127.0.0.1", "203.0.113.9", [])
    assert got == "203.0.113.9"


def test_empty_trusted_list_ignores_xff_for_public_remote(sandbox):
    """Legacy behavior: a public REMOTE_ADDR means XFF is never trusted."""
    got = _client_ip(sandbox, "198.51.100.5", "1.2.3.4", [])
    assert got == "198.51.100.5"


def test_trusted_vps_proxy_yields_real_client_ip(sandbox):
    """The #16 case: REMOTE_ADDR is a listed trusted proxy -> read XFF."""
    got = _client_ip(sandbox, "203.0.113.7", "198.51.100.9", ["203.0.113.7"])
    assert got == "198.51.100.9"


def test_spoofed_xff_from_untrusted_remote_is_ignored(sandbox):
    """Hardening: an attacker connecting directly cannot fake being the proxy."""
    got = _client_ip(sandbox, "198.51.100.66", "203.0.113.7, 10.0.0.1", ["203.0.113.7"])
    assert got == "198.51.100.66"


def test_chained_varnish_and_vps_proxies_both_skipped(sandbox):
    """Hardening: multiple own hops (Varnish + VPS) in one chain are all skipped."""
    got = _client_ip(sandbox, "127.0.0.1", "198.51.100.9, 203.0.113.7", ["203.0.113.7"])
    assert got == "198.51.100.9"


def test_ipv6_client_and_case_insensitive_trust_match(sandbox):
    got = _client_ip(
        sandbox, "2a01:4f8:1c17:aaaa::1", "2001:4860:4860::8888",
        ["2A01:4F8:1C17:AAAA::1"],
    )
    assert got == "2001:4860:4860::8888"


def test_garbage_xff_segments_are_skipped_not_returned(sandbox):
    got = _client_ip(
        sandbox, "203.0.113.7", "not-an-ip, , 198.51.100.9, 203.0.113.7",
        ["203.0.113.7"],
    )
    assert got == "198.51.100.9"
