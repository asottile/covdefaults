import os
import re
import sys
import sysconfig
from collections import OrderedDict
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
        # set source to either:
        # - cwd
        # - installed pkg within purelib/platlib, these map back to src tree
        # https://coverage.readthedocs.io/en/latest/config.html#paths
        source = []
        paths = config.get_option('paths')
        if self._installed_package:
            search_packages = list({
                sysconfig.get_paths()['platlib'],
                sysconfig.get_paths()['purelib'],
            })
            for pkg, dest in self._installed_package.items():
                found = False
                # also check in dest in case this is a develop install
                possible_dir = search_packages + [os.path.abspath(dest)]
                poss_dir_ord = list(
                    OrderedDict(
                        (i, None) for i in sys.path if i in possible_dir
                    ).keys(),
                )
                for path in poss_dir_ord:
                    base = os.path.join(path, pkg)
                    for suffix in ('', '.py'):
                        at = f'{base}{suffix}'
                        if os.path.exists(at):
                            source.append(at)
                            if os.path.isfile(at):
                                src_path = dest
                            else:
                                src_path = os.path.join(dest, pkg)
                            if not os.path.exists(src_path):
                                raise RuntimeError(
                                    'source path {} for {} does not exists'
                                    ''.format(
                                        src_path,
                                        at,
                                    ),
                                )
                            paths[pkg] = [src_path, at]
                            found = True
                            break
                    if found:
                        break
                if not found:
                    raise RuntimeError(
                        f'could not find installed package {pkg}',
                    )

        source.append(os.getcwd())
        config.set_option('run:source', source)
        config.set_option('paths', paths)

    def _fix_omit(self, config: CoverageConfig) -> None:
        omit = set(config.get_option('run:omit') or [])
        omit.add('*/setup.py')  # always ignore setup.py
        omit.add('*/__main__.py')  # always ignore __main__.py

        # ignore common virtual environment folders, unless it's within source
        source = config.get_option('run:source')
        sep = os.sep
        for folder, is_prefix in (
                ('.tox', False),
                ('venv', True),
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
                            if entry == child:  # don't exclude children
                                continue
                            pattern = f'*/{level}/{entry}'
                            if os.path.isdir(os.path.join(level, entry)):
                                pattern += '/*'
                            else:
                                if not entry.endswith('.py'):
                                    continue
                            omit.add(pattern)
                    break
            else:  # blank omit any such folders
                omit.add(f'*/{folder}{"*" if is_prefix else ""}/*')

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
