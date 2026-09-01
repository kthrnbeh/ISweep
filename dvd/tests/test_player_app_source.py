from pathlib import Path


def test_player_app_source_compiles() -> None:
    """Catch syntax errors in the desktop player before launch-time."""

    source_path = Path("dvd/player_app.py")
    source = source_path.read_text(encoding="utf-8")
    compile(source, str(source_path), "exec")
