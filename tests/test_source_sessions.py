from nolan.source_sessions import update_env_text


def test_update_env_text_escapes_cookie_json_and_preserves_other_values():
    original = "OTHER=keep\nRAWPIXEL_COOKIE=old\nRAWPIXEL_CDP_URL=old\n"
    cookie = 'a=1; g_state={"signed":true}; session=secret'
    got = update_env_text(original, {
        "RAWPIXEL_COOKIE": cookie,
        "RAWPIXEL_CDP_URL": "http://127.0.0.1:9222",
    })
    assert "OTHER=keep" in got
    assert 'RAWPIXEL_COOKIE="a=1; g_state={\\"signed\\":true}; session=secret"' in got
    assert 'RAWPIXEL_CDP_URL="http://127.0.0.1:9222"' in got


def test_update_env_text_appends_missing_keys_once():
    got = update_env_text("A=1\n", {"RAWPIXEL_USER_AGENT": "Chrome Test"})
    assert got.count("RAWPIXEL_USER_AGENT=") == 1
    assert got.endswith('RAWPIXEL_USER_AGENT="Chrome Test"\n')
