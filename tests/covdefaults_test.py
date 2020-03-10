import importlib
import re

import pytest
from coverage.config import CoverageConfig
from coverage.config import DEFAULT_EXCLUDE
from coverage.plugin_support import Plugins

import covdefaults

configure = covdefaults.CovDefaults().configure


def test_plat_impl_pragmas():
    pragmas = covdefaults._plat_impl_pragmas()
    assert {p.split()[2] for p in pragmas} == set(covdefaults._ALL)
    # other pragmas
    for s in pragmas[:-3]:
        c, pragma, _, cover = s.split()
        assert (c, pragma, cover) == ('#', 'pragma:', r'cover\b'), s
    # self pragmas
    for s in pragmas[-3:]:
        c, pragma, _, no, cover = s.split()
        assert (c, pragma, no, cover) == ('#', 'pragma:', 'no', r'cover\b'), s


@pytest.fixture
def configured():
    cfg = CoverageConfig()
    configure(cfg)
    return cfg


def test_constant_options(configured):
    assert configured.get_option('run:branch') is True
    assert configured.get_option('run:source') == ['.']
    assert configured.get_option('report:show_missing') is True
    assert configured.get_option('report:skip_covered') is True
    assert configured.get_option('report:fail_under') == 100


def test_extends_existing_omit():
    cfg = CoverageConfig()
    cfg.set_option('run:omit', ['pre_commit/resources/*'])
    configure(cfg)
    assert cfg.get_option('run:omit') == [
        '*/.tox/*',
        '*/__main__.py',
        '*/setup.py',
        '*/venv*/*',
        'pre_commit/resources/*',
    ]


def test_subtract_omit():
    cfg = CoverageConfig()
    covdefaults.CovDefaults(subtract_omit='*/.tox/*').configure(cfg)
    assert cfg.get_option('run:omit') == [
        '*/__main__.py',
        '*/setup.py',
        '*/venv*/*',
    ]


def test_exclude_lines_does_not_include_defaults(configured):
    ret = set(configured.get_option('report:exclude_lines'))
    assert set(DEFAULT_EXCLUDE) & ret == set()


@pytest.mark.parametrize(
    'src',
    (
        'if x:  # pragma: no cover\n',
        'if x:  # pragma: no cover (py38+)\n',
        'if x:  # noqa  # pragma: no cover\n',
        'if x:  # pragma: no cover  # noqa\n',
        'raise AssertionError("unreachable!")\n',
        'raise NotImplementedError("TODO!")\n',
        '    return NotImplemented\n',
        '    raise\n',
        'if False:\n',
        'if TYPE_CHECKING:\n',
        'def f(x: int) -> int: ...\n',
        'def f(x: int) -> int:\n    ...\n',
        'def never_returns() -> NoReturn:\n',
        'def never_returns() -> "NoReturn":\n',
        "def never_returns() -> 'NoReturn':\n",
        'if __name__ == "__main__":\n',
        "if __name__ == '__main__':\n",
    ),
)
def test_excludes_lines(configured, src):
    for reg in configured.get_option('report:exclude_lines'):
        if any(re.search(reg, line) for line in src.splitlines()):
            break
    else:
        raise AssertionError(f'no regex matched {src!r}')


def test_extends_existing_exclude_lines():
    cfg = CoverageConfig()
    cfg.set_option('report:exclude_lines', ['^if MYPY:$'])
    configure(cfg)
    assert '^if MYPY:$' in cfg.get_option('report:exclude_lines')


def test_configure_keeps_existing_fail_under():
    cfg = CoverageConfig()
    cfg.set_option('report:fail_under', 42)
    configure(cfg)
    assert cfg.get_option('report:fail_under') == 42


def test_coverage_init():
    cfg = CoverageConfig()
    plugin_manager = Plugins.load_plugins(['covdefaults'], cfg)
    assert plugin_manager.get('covdefaults.CovDefaults')


def test_fix_coverage():
    """since we get imported as a coverage plugin -- need to re-scan module"""
    importlib.reload(covdefaults)
