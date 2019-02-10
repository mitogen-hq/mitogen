
import sys
# Add viewBox attr to SVGs lacking it, so IE scales properly.

import lxml.etree
import glob


for name in sys.argv[1:]:  # glob.glob('*/*.svg'): #+ glob.glob('images/ansible/*.svg'):
    doc = lxml.etree.parse(open(name))
    svg = doc.getroot()
    for elem in svg.cssselect('[stroke-width]'):
        if elem.attrib['stroke-width'] < '2':
            elem.attrib['stroke-width'] = '2'

    open(name, 'w').write(lxml.etree.tostring(svg, xml_declaration=True, encoding='UTF-8'))
