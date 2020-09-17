"""
Import all modules under this package.

This package contains all modules responsible for retrieving custom
device information for particular GPC services.

"""

from os.path import dirname, basename, isfile, join
import glob

MODULES = glob.glob(join(dirname(__file__), "*.py"))

__all__ = [basename(f)[:-3] for f in MODULES if isfile(f) and not f.endswith("__init__.py")]
