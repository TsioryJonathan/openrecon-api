"""Tests for the sherlock sites endpoint and site validation (pure, no DB)."""

import asyncio

import pytest
from fastapi import HTTPException

from app.categories import SHERLOCK_CATEGORIES
from app.constants import SHERLOCK_SITES
from app.routers.sherlock import SearchRequest, get_sites, search_username


def test_sites_total_matches_category_sum():
    payload = asyncio.run(get_sites())
    total = sum(len(c["sites"]) for c in payload["categories"])
    assert payload["total"] == total


def test_sites_total_matches_constant_set():
    payload = asyncio.run(get_sites())
    assert payload["total"] == len(SHERLOCK_SITES)


def test_sites_no_duplicates_across_categories():
    seen: set[str] = set()
    for cat in SHERLOCK_CATEGORIES.values():
        for site in cat:
            assert site not in seen, f"duplicate site: {site}"
            seen.add(site)


def test_sites_is_a_substantial_catalog():
    # The README advertises the catalog in the hundreds; guard against a
    # truncated or accidentally emptied categories module.
    payload = asyncio.run(get_sites())
    assert payload["total"] >= 400


def test_search_rejects_unknown_site():
    body = SearchRequest(username="john_doe", sites=["NotARealPlatform"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(search_username(body))
    assert exc.value.status_code == 400
    assert "NotARealPlatform" in exc.value.detail
