"""Tests for firebase.py (URL construction only — no network calls)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import urllib.parse
from firebase import _fb_url, today_key
import datetime


# ── _fb_url ──────────────────────────────────────────────────────────

CFG = {"firebase_url": "https://mydb.firebaseio.com", "firebase_path": "my/path"}

def test_fb_url_basic():
    url = _fb_url(CFG, "config/sheets")
    assert url == "https://mydb.firebaseio.com/my/path/config/sheets.json"

def test_fb_url_trailing_slash_stripped():
    cfg = {**CFG, "firebase_url": "https://mydb.firebaseio.com/"}
    url = _fb_url(cfg, "config")
    assert not url.startswith("https://mydb.firebaseio.com//")

def test_fb_url_path_leading_slash_stripped():
    cfg = {**CFG, "firebase_path": "/my/path/"}
    url = _fb_url(cfg, "config")
    assert url == "https://mydb.firebaseio.com/my/path/config.json"

def test_fb_url_pipe_encoded():
    url = _fb_url(CFG, "scores/M|3MGM")
    # pipe in node part must be encoded; slashes preserved
    assert "%7C" in url
    assert "scores/M%7C3MGM" in url

def test_fb_url_korean_encoded():
    url = _fb_url(CFG, "obs/M|3MGM|김철수")
    assert urllib.parse.quote("김철수") in url

def test_fb_url_slash_preserved_in_node():
    url = _fb_url(CFG, "config/sheets/M/classes")
    assert "config/sheets/M/classes.json" in url

def test_fb_url_missing_config_keys():
    url = _fb_url({}, "config")
    assert url.endswith("config.json")


# ── today_key ────────────────────────────────────────────────────────

def test_today_key_format():
    key = today_key()
    parts = key.split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 4  # YYYY
    assert len(parts[1]) == 2  # MM
    assert len(parts[2]) == 2  # DD

def test_today_key_is_today():
    assert today_key() == datetime.date.today().isoformat()
