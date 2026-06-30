from app.tasks.analytics import anonymize_ip


def test_anonymize_ipv4():
    assert anonymize_ip("203.0.113.44") == "203.0.113.0"


def test_anonymize_ipv6():
    assert anonymize_ip("2001:db8:abcd:1234:1111:2222:3333:4444") == ("2001:db8:abcd:1234::")


def test_anonymize_invalid_ip():
    assert anonymize_ip("not-an-ip") is None
