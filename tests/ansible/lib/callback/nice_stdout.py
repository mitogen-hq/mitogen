from __future__ import unicode_literals
import os
import io

from ansible.module_utils import six

try:
    from ansible.plugins import callback_loader
except ImportError:
    from ansible.plugins.loader import callback_loader

try:
    pprint = __import__(os.environ['NICE_STDOUT_PPRINT'])
except KeyError:
    pprint = None


def printi(tio, obj, key=None, indent=0):
    def write(s, *args):
        if args:
            s %= args
        tio.write('  ' * indent)
        if key is not None:
            tio.write('%s: ' % (key,))
        tio.write(s)
        tio.write('\n')

    if isinstance(obj, (list, tuple)):
        write('[')
        for i, obj2 in enumerate(obj):
            printi(tio, obj2, key=i, indent=indent+1)
        key = None
        write(']')
    elif isinstance(obj, dict):
        write('{')
        for key2, obj2 in sorted(six.iteritems(obj)):
            if not (key2.startswith('_ansible_') or
                    key2.endswith('_lines')):
                printi(tio, obj2, key=key2, indent=indent+1)
        key = None
        write('}')
    elif isinstance(obj, six.text_type):
        for line in obj.splitlines():
            write('%s', line.rstrip('\r\n'))
    elif isinstance(obj, six.binary_type):
        obj = obj.decode('utf-8', 'replace')
        for line in obj.splitlines():
            write('%s', line.rstrip('\r\n'))
    else:
        write('%r', obj)


DefaultModule = callback_loader.get('default', class_only=True)

class CallbackModule(DefaultModule):
    def _dump_results(self, result, *args, **kwargs):
        try:
            tio = io.StringIO()
            if pprint:
                pprint.pprint(result, stream=tio)
            else:
                printi(tio, result)
            return tio.getvalue() #.encode('ascii', 'replace')
        except:
            import traceback
            traceback.print_exc()
            raise
