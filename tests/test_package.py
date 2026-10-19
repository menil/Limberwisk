import pytest

import muteme_flow
from muteme_flow.__main__ import main


def test_version_is_exposed():
    assert muteme_flow.__version__


def test_version_flag_prints_the_version_without_starting_the_app(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert muteme_flow.__version__ in capsys.readouterr().out
