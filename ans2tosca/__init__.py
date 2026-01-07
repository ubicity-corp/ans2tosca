from importlib.metadata import version, PackageNotFoundError

def get_live_version(root_path="."):
    """Calculates version live from Git when running from source."""
    try:
        from setuptools_scm import get_version
        # Get the version directly from the Git repository state
        #return get_version(root=root_path, fallback_local_scheme='dirty-tag')
        return get_version(root=root_path)
    except (ModuleNotFoundError, LookupError):
        # Fallback if setuptools_scm isn't installed or repo not found
        return "0.0.0+no-scm"

try:
    # 1. First, try to read the version from installed package metadata
    __version__ = version("ans2tosca") 
except PackageNotFoundError:
    # 2. If not installed, fall back to calculating the version live from Git
    __version__ = get_live_version(root_path=".") 

# The root_path="." is important. 
# It tells setuptools_scm to look one level up from __init__.py 

#print(f"Package initialized. Version: {__version__}")
