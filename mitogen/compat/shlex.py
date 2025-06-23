try:
    from shlex import quote as shlex_quote
except ImportError:
    from pipes import quote as shlex_quote
