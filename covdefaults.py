import os
import sys
from typing import Any
from typing import Dict
from typing import List
from typing import Tuple

from coverage import CoveragePlugin
from coverage.config import CoverageConfig
from coverage.config import DEFAULT_EXCLUDE
from coverage.plugin_support import Plugins

_ALL = (
    # os.name
    'nt', 'posix',
    # sys.platform
    'cygwin', 'darwin', 'linux', 'msys', 'win32',
    # sys.implementation.name
    'cpython', 'pypy',
)


def _plat_impl_pragmas():  # type: () -> List[str]
    tags = {os.name, sys.platform, sys.implementation.name}
    ret = [fr'# pragma: {tag} cover\b' for tag in _ALL if tag not in tags]
    ret.extend(fr'# pragma: {tag} no cover\b' for tag in tags)
    return ret


OPTIONS: Tuple[Tuple[str, Any], ...] = (
    ('run:branch', True),

    ('report:show_missing', True),
    ('report:skip_covered', True),
)
EXTEND = (
    ('run:omit', ['*/__main__.py', '*/setup.py']),
    (
        'report:exclude_lines',
        [
            # a more strict default pragma
            r'# pragma: no cover\b',
            # allow defensive code
            r'^\s*raise AssertionError\b',
            r'^\s*raise NotImplementedError\b',
            r'^\s*return NotImplemented\b',
            r'^\s*raise$',
            # typing-related code
            r'^if (False|TYPE_CHECKING):',
            r': \.\.\.(\s*#.*)?$',
            r'^ +\.\.\.$',
            r'-> [\'"]?NoReturn[\'"]?:',
            # non-runnable code
            r'^if __name__ == [\'"]__main__[\'"]:$',
            *_plat_impl_pragmas(),
        ],
    ),
)


class CovDefaults(CoveragePlugin):
    def __init__(self, subtract_omit: str = '') -> None:
        self._subtract_omit = subtract_omit.split()

    def configure(self, config: CoverageConfig) -> None:
        for k, v in OPTIONS:
            config.set_option(k, v)
        if config.get_option('run:source') is None:
            config.set_option('run:source', ['.'])
        for k, v in EXTEND:
            before = set(config.get_option(k) or ())
            before.update(v)
            config.set_option(k, sorted(before))

        # subtract omit settings if requested
        if self._subtract_omit:
            omit = set(config.get_option('run:omit'))
            omit.difference_update(self._subtract_omit)
            config.set_option('run:omit', sorted(omit))

        # remove DEFAULT_EXCLUDE, we add a more-strict casing
        exclude = set(config.get_option('report:exclude_lines'))
        exclude.difference_update(DEFAULT_EXCLUDE)
        config.set_option('report:exclude_lines', sorted(exclude))

        # fail_under: if they specify a value then honor it
        if not config.get_option('report:fail_under'):
            config.set_option('report:fail_under', 100)


def coverage_init(reg: Plugins, options: Dict[str, str]) -> None:
    reg.add_configurer(CovDefaults(**options))
