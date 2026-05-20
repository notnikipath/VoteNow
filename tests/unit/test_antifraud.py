from shared.votenow_common import check_captcha, duplicate_fingerprint, is_ip_rate_limited, register_ip_submission


def test_captcha() -> None:
    assert check_captcha("ok", True, "secret")
    assert not check_captcha(None, True, "secret")


def test_duplicate_fingerprint() -> None:
    fp = duplicate_fingerprint("SURVEY-1", "usr-1", None, None, "127.0.0.1")
    assert fp == "SURVEY-1:usr-1"


def test_ip_rate_limit() -> None:
    store: dict[str, list] = {}
    register_ip_submission(store, "S1", "10.0.0.1")
    assert not is_ip_rate_limited(store, "S1", "10.0.0.1", 2)
    register_ip_submission(store, "S1", "10.0.0.1")
    assert is_ip_rate_limited(store, "S1", "10.0.0.1", 2)
