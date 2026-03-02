try:
    import in_try
    from in_try import x as y, z
except ImportError:
    import in_except_importerror
    from in_except_importerror import x as y, z
except Exception:
    import in_except_exception
    from in_except_exception import x as y, z
