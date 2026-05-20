from shared.votenow_common import decrypt_text, encrypt_text, sign_token, verify_token


def test_encrypt_roundtrip() -> None:
    source = "email@example.com"
    encrypted = encrypt_text(source, "demo-key")
    assert encrypted != source
    assert decrypt_text(encrypted, "demo-key") == source


def test_token_roundtrip() -> None:
    token = sign_token({"sub": "mod-1", "role": "moderator"}, "jwt-key", exp_minutes=5)
    payload = verify_token(token, "jwt-key")
    assert payload is not None
    assert payload["sub"] == "mod-1"
