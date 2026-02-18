import pytest
from utils import sanitize, password_check


def test_sanitize_removes_script_tags():
    malicious = '<script>alert("xss")</script><b>ok</b>'
    cleaned = sanitize(malicious)
    assert 'script' not in cleaned.lower()
    assert 'ok' in cleaned


def test_sanitize_none_returns_empty():
    assert sanitize(None) == ''


def test_password_check_accepts_strong():
    strong = 'Secur3!Passw0rd'
    res = password_check(strong)
    assert res['password_ok'] is True
    assert not res['length_error']


def test_password_check_rejects_weak():
    weak = 'short'
    res = password_check(weak)
    assert res['password_ok'] is False
    assert res['length_error']

