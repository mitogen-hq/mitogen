# coding=UTF-8

# Generate the fragment used to make email release announcements
# usage: release-notes.py 0.2.6

import sys
import urllib
import lxml.html

import subprocess


response = urllib.urlopen('https://mitogen.networkgenomics.com/changelog.html')
tree = lxml.html.parse(response)

prefix = 'v' + sys.argv[1].replace('.', '-')

for elem in tree.getroot().cssselect('div.section[id]'):
    if elem.attrib['id'].startswith(prefix):
        break
else:
    print('cant find')



for child in tree.getroot().cssselect('body > *'):
    child.getparent().remove(child)

body, = tree.getroot().cssselect('body')
body.append(elem)

proc = subprocess.Popen(
    args=['w3m', '-T', 'text/html', '-dump', '-cols', '72'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
)

stdout, _ = proc.communicate(input=(lxml.html.tostring(tree)))
stdout = stdout.decode('UTF-8')
stdout = stdout.translate({
    ord(u'¶'): None,
    ord(u'•'): ord(u'*'),
    ord(u'’'): ord(u"'"),
    ord(u'“'): ord(u'"'),
    ord(u'”'): ord(u'"'),
})
print(stdout)
