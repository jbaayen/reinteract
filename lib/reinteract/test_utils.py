def assert_equals(result, expected):
    if result != expected:
        raise AssertionError("Got %r, expected %r" % (result, expected))
