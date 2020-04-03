__all__ = ('__version__', 'DataModel')

from pbr.version import VersionInfo

from . import patches  # noqa
from .datamodel import DataModel  # noqa

# Check the PBR version module docs for other options than release_string()
__version__ = VersionInfo('flask-restless-datamodel').release_string()
