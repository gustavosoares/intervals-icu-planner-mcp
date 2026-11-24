from intervals_icu_planner_mcp.config import find_api_key, parse_dotenv


def test_parse_dotenv():
    text = """
# comment
INTERVALS_API_KEY=abc123
export OTHER="quoted value"
SINGLE='x # not a comment'
TRAIL=val # comment
EMPTY=
garbage line
"""
    assert parse_dotenv(text) == {
        "INTERVALS_API_KEY": "abc123",
        "OTHER": "quoted value",
        "SINGLE": "x # not a comment",
        "TRAIL": "val",
        "EMPTY": "",
    }


def test_env_var_wins(tmp_path):
    f = tmp_path / ".env"
    f.write_text("INTERVALS_API_KEY=fromfile\n")
    assert find_api_key({"INTERVALS_API_KEY": "fromenv"}, str(f)) == "fromenv"


def test_falls_back_to_dotenv(tmp_path):
    f = tmp_path / ".env"
    f.write_text("INTERVALS_API_KEY=fromfile\n")
    assert find_api_key({}, str(f)) == "fromfile"


def test_no_key(tmp_path):
    assert find_api_key({}, str(tmp_path / "missing.env")) is None
