"""Shared git and dependency shim for the evals.

The evals spawn git to build throwaway repos. On an Apple Silicon Mac running an
x86_64 Python, git's xcrun shim cannot load its arm64-only dylib and every call
fails with "unable to load libxcrun". Every script under skills/ already carries
this fallback; the evals need it too, or their published numbers cannot be
reproduced on that machine.
"""
import subprocess
import sys

# The evals commit as a fixed identity so they never depend on the user's config.
IDENT = ['-c', 'user.email=a@b', '-c', 'user.name=a']


def git(args, cwd, check=True, text=True):
    """Run git in cwd, retrying under arch -arm64 when the native call fails."""
    base = ['git'] + list(args)
    p = None
    try:
        p = subprocess.run(base, cwd=cwd, capture_output=True, text=text)
    except (FileNotFoundError, OSError):
        pass
    if p is None or (p.returncode != 0 and sys.platform == 'darwin'):
        try:
            alt = subprocess.run(['arch', '-arm64'] + base, cwd=cwd, capture_output=True, text=text)
            if p is None or alt.returncode == 0:
                p = alt
        except OSError:
            pass
    if p is None:
        raise RuntimeError('git is not available')
    if check and p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, base, p.stdout, p.stderr)
    return p


def have_module(name):
    """True if `name` imports in the interpreter the evals shell out to."""
    return subprocess.run([sys.executable, '-c', 'import %s' % name],
                          capture_output=True).returncode == 0


def require(name, eval_name):
    """Print a clear skip line and return False when a dependency is missing."""
    if have_module(name):
        return True
    print('%s: SKIPPED - needs %s (pip install %s)' % (eval_name, name, name))
    return False
