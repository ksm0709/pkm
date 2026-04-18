from pathlib import Path
from unittest.mock import patch
from pkm.commands.setup import install_shell_aliases


def test_install_shell_aliases(tmp_path: Path):
    # Mock Path.home() to return tmp_path
    with patch("pkm.commands.setup.Path.home", return_value=tmp_path):
        bashrc = tmp_path / ".bashrc"
        zshrc = tmp_path / ".zshrc"
        bashrc.write_text("some content\n")
        zshrc.write_text("some content\n")

        install_shell_aliases()

        assert "alias pkmcd='cd $(pkm vault where)'" in bashrc.read_text()
        assert "alias pkmcd='cd $(pkm vault where)'" in zshrc.read_text()

        # Run again, should not add duplicate
        install_shell_aliases()
        assert bashrc.read_text().count("alias pkmcd='cd $(pkm vault where)'") == 1
