import pytest

import limberwisk
from limberwisk.__main__ import main


def test_version_is_exposed():
    assert limberwisk.__version__


def test_version_flag_prints_the_version_without_starting_the_app(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert limberwisk.__version__ in capsys.readouterr().out
