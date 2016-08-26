
import os
import sys

import econtext
import econtext.master
import econtext.utils


import sys
sys.path.insert(0, '..')


def serve_django_app(settings_name):
    os.listdir = lambda path: []

    os.environ['DJANGO_SETTINGS_MODULE'] = settings_name
    import django
    args = ['manage.py', 'runserver', '0:9191', '--noreload']
    from django.conf import settings
    #settings.configure()
    django.setup()
    from django.core.management.commands import runserver
    runserver.Command().run_from_argv(args)
    #django.core.management.execute_from_command_line(args)


def main(broker):
    import logging
    econtext.utils.log_to_file(level=logging.INFO, io=False)
    context = econtext.master.connect(broker)
    context.call(os.chdir, '/')
    #context.call(econtext.utils.log_to_file, '/tmp/log')
    context.call(serve_django_app, 'webproject.settings')

if __name__ == '__main__' and not econtext.slave:
    econtext.utils.run_with_broker(main)
