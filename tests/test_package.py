import muteme_flow
from muteme_flow.__main__ import main


def test_version_is_exposed():
    assert muteme_flow.__version__


def test_main_prints_the_version(capsys):
    main()
    assert muteme_flow.__version__ in capsys.readouterr().out
