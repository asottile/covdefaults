import os
import re
import sys
from distutils.dist import Distribution
from typing import Dict
from typing import List
from typing import Optional
from typing import Set

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
    def _parse_inst_pkg(installed_package: str) -> Dict[str, Optional[str]]:
        result: Dict[str, Optional[str]] = {}
        for entry in installed_package.split(' '):
            if entry:
                key, value = entry, None
                if entry.count(':') == 1:
                    key, value = entry.split(':')
                result[key] = value
        return result

    def configure(self, config: CoverageConfig) -> None:
        self._set_source(config)
        for opt_k, opt_v in OPTIONS:
            config.set_option(opt_k, opt_v)
        for k, v in EXTEND:
            before = set(config.get_option(k) or ())
            before.update(v)
            config.set_option(k, sorted(before))

        self.fix_omit(config)

        # remove DEFAULT_EXCLUDE, we add a more-strict casing
        exclude = set(config.get_option('report:exclude_lines'))
        exclude.difference_update(DEFAULT_EXCLUDE)
        config.set_option('report:exclude_lines', sorted(exclude))

        # fail_under: if they specify a value then honor it
        if not config.get_option('report:fail_under'):
            config.set_option('report:fail_under', 100)

    def fix_omit(self, config: CoverageConfig) -> None:
        # subtract omit settings if requested
        omit = set(config.get_option('run:omit') or [])
        omit.add('*/setup.py')  # always ignore setup.py

        # ignore common virtual environment folders, unless it's within source
        source = config.get_option('run:source')
        sep, suf = os.sep, ['.py', '.pyc', '.pyo']
        for folder, is_prefix in (
                ('.tox', False),
                ('.nox', False),
                ('venv', True),
                ('.venv', True),
        ):
            matcher = re.compile(f'.*{re.escape(f"{sep}{folder}{sep}")}.*')
            for src in source:
                if matcher.match(src) is not None:
                    # now we can't cover this with one omit,
                    # climb the tree and exclude everything else
                    parts = os.path.relpath(src, os.getcwd()).split(sep)
                    for at in range(1, len(parts)):
                        level = sep.join(parts[:at])
                        child = parts[at]
                        for entry in os.listdir(level):
                            if entry == child:  # dont' exclude children
                                continue
                            pattern = f'*/{level}/{entry}'
                            if os.path.isdir(os.path.join(level, entry)):
                                pattern += '/*'
                            else:
                                if not any(entry.endswith(e) for e in suf):
                                    continue
                            omit.add(pattern)
                    break
            else:  # blank omit any such folders
                omit.add(f'*/{folder}{"*" if is_prefix else ""}/*')

        omit.difference_update(self._subtract_omit)
        config.set_option('run:omit', sorted(omit))

    def _set_source(self, config: CoverageConfig) -> None:
        if not isinstance(config, CoverageConfig):  # pragma: no cover
            # https://github.com/nedbat/coveragepy/issues/967
            config = config.config
        source = []
        if self._installed_package:
            for path in _get_install_paths():
                for pkg, dest in self._installed_package.items():
                    base = os.path.join(path, pkg)
                    for suffix in ('', '.py'):
                        at = f'{base}{suffix}'
                        if os.path.exists(at):
                            source.append(at)
                            if dest is not None:
                                src_path = os.path.join(dest, pkg)
                                config.paths[pkg] = [src_path, at]
        # set paths to map to cwd
        # https://coverage.readthedocs.io/en/latest/config.html#paths
        source.append(os.getcwd())
        config.set_option('run:source', source)


def _get_install_paths() -> Set[str]:
    # follow what virtualenv uses
    distribution = Distribution({'script_args': '--no-user-cfg'})
    # disable macOS static paths for framework
    if hasattr(sys, '_framework'):  # pragma: no cover
        sys._framework = None  # type:ignore # pragma: no cover
    install = distribution.get_command_obj('install', create=True)
    if install is None:  # pragma: no cover
        return set()  # pragma: no cover
    install.prefix = sys.prefix  # type:ignore
    install.finalize_options()
    return {install.install_platlib, install.install_purelib}  # type:ignore


def coverage_init(reg: Plugins, options: Dict[str, str]) -> None:
    reg.add_configurer(CovDefaults(**options))
