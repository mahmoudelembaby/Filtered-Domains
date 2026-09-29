import pytest
from app.security.ssrf import resolve_and_validate, SSRFError, check_hostname_syntax


def test_blocked_names():
    for h in ["localhost", "foo.internal", "x.local", "single", "a.lan"]:
        with pytest.raises(SSRFError):
            check_hostname_syntax(h)


@pytest.mark.asyncio
async def test_private_ip_blocked():
    # 127.0.0.1 resolves locally; must be rejected without fetching
    with pytest.raises(SSRFError):
        await resolve_and_validate("127.0.0.1")
