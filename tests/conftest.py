from hashlib import sha256

# pytest writes the running test's full nodeid into PYTEST_CURRENT_TEST for every
# setup/call/teardown phase (_pytest/runner.py:_update_current_test_var). Windows caps a
# single environment variable at 32767 characters and raises ValueError past it, so an
# oversized nodeid turns a passing test into a teardown error on Windows only -- the same
# suite stays green in the Linux container, which is how this stayed hidden until C3.
#
# Any large bytes/str parameter reaches the nodeid verbatim: test_catalog.py feeds
# MAX_CATALOG_BYTES+1 (12 MiB) to check the size limit, producing one nodeid of 12,583,008
# characters. Shorten the value where the id is made rather than rewriting _nodeid after
# collection: _nodeid also backs Node.__hash__, the --lf cache and -k matching, so patching
# it late makes those disagree with what the report shows.
#
# Ordering is load-bearing and was verified against the installed pytest (9.1.1):
# _idval_from_hook runs before _idval_from_value (which is what inlines the payload), and
# after _idval_from_function, so an explicit ids= on a parametrize still wins.

# The longest of the 348 collected nodeids is 305 characters once the 12 MiB case above is
# excluded, and no single parameter value comes close to this bound. It catches the
# pathological case without renaming anything that exists today.
MAX_PARAMETRIZE_ID_LENGTH = 256


def pytest_make_parametrize_id(config, val, argname):
    """Give oversized bytes/str parameters a short, stable id. None means no opinion."""
    if not isinstance(val, (bytes, str)) or len(val) <= MAX_PARAMETRIZE_ID_LENGTH:
        return None
    # Keep the size and a digest: a failure still identifies which value was used, and the
    # id stays stable across runs so --lf and -k keep working.
    digest = sha256(val if isinstance(val, bytes) else val.encode('utf-8')).hexdigest()
    return f'{argname}-len{len(val)}-{digest[:12]}'
