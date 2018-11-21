
# Add viewBox attr to SVGs lacking it, so IE scales properly.

import lxml.etree
import glob


for name in glob.glob('images/*.svg') + glob.glob('images/ansible/*.svg'):
    doc = lxml.etree.parse(open(name))
    svg = doc.getroot()
    if 'viewBox' not in svg.attrib:
        svg.attrib['viewBox'] = '0 0 %(width)s %(height)s' % svg.attrib
        open(name, 'w').write(lxml.etree.tostring(svg, xml_declaration=True, encoding='UTF-8'))
