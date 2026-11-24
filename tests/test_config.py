from intervals_icu_planner_mcp.config import ENV_VAR, LEGACY_ENV_VAR, find_api_key, parse_dotenv


def test_parse_dotenv():
    text = """
# comment
INTERVALS_ICU_API_KEY=abc123
export OTHER="quoted value"
SINGLE='x # not a comment'
TRAIL=val # comment
EMPTY=
garbage line
"""
    assert parse_dotenv(text) == {
        "INTERVALS_ICU_API_KEY": "abc123",
        "OTHER": "quoted value",
        "SINGLE": "x # not a comment",
        "TRAIL": "val",
        "EMPTY": "",
    }


def test_env_var_wins(tmp_path):
    f = tmp_path / ".env"
    f.write_text(f"{ENV_VAR}=fromfile\n")
    assert find_api_key({ENV_VAR: "fromenv"}, str(f)) == "fromenv"


def test_falls_back_to_dotenv(tmp_path):
    f = tmp_path / ".env"
    f.write_text(f"{ENV_VAR}=fromfile\n")
    assert find_api_key({}, str(f)) == "fromfile"


def test_no_key(tmp_path):
    assert find_api_key({}, str(tmp_path / "missing.env")) is None


def test_legacy_name_still_works_and_warns_without_the_key(tmp_path):
    warnings: list[str] = []
    key = find_api_key({LEGACY_ENV_VAR: "secret-legacy"}, str(tmp_path / "none"), warnings.append)
    assert key == "secret-legacy"
    assert len(warnings) == 1
    assert ENV_VAR in warnings[0]
    assert "secret-legacy" not in warnings[0]


def test_new_name_beats_legacy(tmp_path):
    f = tmp_path / ".env"
    f.write_text(f"{ENV_VAR}=new\n")
    warnings: list[str] = []
    assert find_api_key({LEGACY_ENV_VAR: "old"}, str(f), warnings.append) == "new"
    assert warnings == []
