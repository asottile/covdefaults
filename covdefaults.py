import os
import sys
import sysconfig
from typing import Dict
from typing import List

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


OPTIONS = (
    ('run:branch', True),
    ('report:show_missing', True),
    ('report:skip_covered', True),
)
EXTEND = (
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
            r': \.\.\.$',
            r'^ +\.\.\.$',
            r'-> [\'"]?NoReturn[\'"]?:',
            # non-runnable code
            r'^if __name__ == [\'"]__main__[\'"]:$',
            *_plat_impl_pragmas(),
        ],
    ),
)


class CovDefaults(CoveragePlugin):
    def __init__(
            self,
            subtract_omit: str = '',
            installed_package: str = '',
    ) -> None:
        self._subtract_omit = subtract_omit.split()
        self._installed_package = self._parse_inst_pkg(installed_package)

    @staticmethod
    def _parse_inst_pkg(installed_package: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for entry in installed_package.split():
            key, value = entry, '.'
            if entry.count(':') == 1:
                key, value = entry.split(':')
            result[key] = value
        return result

    def _set_source(self, config: CoverageConfig) -> None:
        if self._installed_package:
            source = set(self._installed_package)
            configured_dirs = set(self._installed_package.values())
            for path in os.listdir('.'):
                if (
                        (os.path.isdir(path) or path.endswith('.py')) and
                        # replicate the `source = .` `omit=` setting
                        path not in {'setup.py', '.tox'} and
                        not path.startswith('venv') and
                        path not in configured_dirs
                ):
                    source.add(path)
            config.set_option('run:source', sorted(source))
            sysconfig_paths = sysconfig.get_paths()
            libdirs = {sysconfig_paths['platlib'], sysconfig_paths['purelib']}
            paths = {
                f'covdefaults_{pkg}': [dest, *libdirs]
                for pkg, dest in self._installed_package.items()
            }
            config.set_option('paths', paths)
        else:
            config.set_option('run:source', [os.getcwd()])

    def _fix_omit(self, config: CoverageConfig) -> None:
        omit = set(config.get_option('run:omit') or [])
        omit.update(('*/setup.py', '*/__main__.py'))

        if not self._installed_package:
            omit.update(('*/.tox/*', '*/venv*/*'))

        omit.difference_update(self._subtract_omit)
        config.set_option('run:omit', sorted(omit))

    def configure(self, config: CoverageConfig) -> None:
        self._set_source(config)
        for opt_k, opt_v in OPTIONS:
            config.set_option(opt_k, opt_v)
        for k, v in EXTEND:
            before = set(config.get_option(k) or ())
            before.update(v)
            config.set_option(k, sorted(before))
        self._fix_omit(config)

        # remove DEFAULT_EXCLUDE, we add a more-strict casing
        exclude = set(config.get_option('report:exclude_lines'))
        exclude.difference_update(DEFAULT_EXCLUDE)
        config.set_option('report:exclude_lines', sorted(exclude))

        # fail_under: if they specify a value then honor it
        if not config.get_option('report:fail_under'):
            config.set_option('report:fail_under', 100)


def coverage_init(reg: Plugins, options: Dict[str, str]) -> None:
    reg.add_configurer(CovDefaults(**options))
