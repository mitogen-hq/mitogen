"""
On the Mitogen master, this is imported from ``mitogen/__init__.py`` as would
be expected. On the slave, it is built dynamically during startup.
"""

#: This is ``False`` in slave contexts. It is used in single-file Python
#: programs to avoid reexecuting the program's :py:func:`main` function in the
#: slave. For example:
#:
#:      .. code-block:: python
#:
#:          def do_work():
#:              os.system('hostname')
#:
#:          def main(broker):
#:              context = mitogen.master.connect(broker)
#:              context.call(do_work)  # Causes slave to import __main__.
#:
#:          if __name__ == '__main__' and mitogen.is_master:
#:              import mitogen.utils
#:              mitogen.utils.run_with_broker(main)
#:
is_master = True


#: This is ``0`` in a master, otherwise it is a master-generated ID unique to
#: the slave context used for message routing.
context_id = 0


#: This is ``None`` in a master, otherwise it is the master-generated ID unique
#: to the slave's parent context.
parent_id = None


#: This is an empty list in a master, otherwise it is a list of parent context
#: IDs ordered from most direct to least direct.
parent_ids = []
