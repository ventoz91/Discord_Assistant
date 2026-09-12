from webpanel.auth import hash_password, verify_password


def test_correct_password_verifies():
    stored = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", stored)


def test_wrong_password_rejected():
    stored = hash_password("correct horse battery staple")
    assert not verify_password("wrong password", stored)


def test_hash_is_salted_differently_each_time():
    a = hash_password("same password")
    b = hash_password("same password")
    assert a != b
    assert verify_password("same password", a)
    assert verify_password("same password", b)


def test_verify_rejects_garbage_stored_value():
    assert not verify_password("anything", "not-a-real-hash")
