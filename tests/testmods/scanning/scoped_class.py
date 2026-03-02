class C:
    import in_class
    from in_class import x as y

    def m(self):
        import in_method
        from in_method import x as y, z
