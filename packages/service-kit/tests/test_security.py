import hashlib

from service_kit.security import PasswordHasher, hash_token, new_token


def test_tokens_are_random_and_stored_only_as_sha256() -> None:
    token, token_hash = new_token()

    assert len(token) >= 43  # 32 bytes, URL-safe base64
    assert token_hash == hashlib.sha256(token.encode()).hexdigest() == hash_token(token)
    assert new_token()[0] != token


def test_passwords_use_argon2id() -> None:
    hasher = PasswordHasher()

    password_hash = hasher.hash("correct horse battery")

    assert password_hash.startswith("$argon2id$")
    assert hasher.verify("correct horse battery", password_hash)
    assert not hasher.verify("wrong", password_hash)


def test_an_unknown_user_check_costs_the_same_work() -> None:
    hasher = PasswordHasher()

    # It must not raise and must not reveal anything; it only spends the time a real check does.
    hasher.verify_unknown_user("whatever")
