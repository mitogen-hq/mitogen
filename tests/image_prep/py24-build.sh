#!/bin/bash
# Build the tests/data/ubuntu-python-2.4.6.tar.bz2 tarball.

set -ex

wget -cO setuptools-1.4.2.tar.gz https://files.pythonhosted.org/packages/source/s/setuptools/setuptools-1.4.2.tar.gz
wget -cO ez_setup.py https://raw.githubusercontent.com/pypa/setuptools/bootstrap-py24/ez_setup.py
wget -cO simplejson-2.0.9.tar.gz https://github.com/simplejson/simplejson/archive/v2.0.9.tar.gz
wget -cO psutil-2.1.3.tar.gz https://github.com/giampaolo/psutil/archive/release-2.1.3.tar.gz
wget -cO unittest2-0.5.1.zip http://voidspace.org.uk/downloads/unittest2-0.5.1-python2.3.zip
wget -cO cpython-2.4.6.tar.gz https://github.com/python/cpython/archive/v2.4.6.tar.gz
wget -cO mock-0.8.0.tar.gz https://github.com/testing-cabal/mock/archive/0.8.0.tar.gz

tar xzvf cpython-2.4.6.tar.gz

(
    cd cpython-2.4.6
    ./configure --prefix=/usr/local/python2.4.6 --with-pydebug --enable-debug CFLAGS="-g -O0" # --enable-debug 
    echo 'zlib zlibmodule.c -I$(prefix)/include -L$(exec_prefix)/lib -lz' >> Modules/Setup.config
    make -j 8
    sudo make install
)

sudo /usr/local/python2.4.6/bin/python2.4 ez_setup.py
sudo /usr/local/python2.4.6/bin/easy_install -Z psutil-2.1.3.tar.gz
sudo /usr/local/python2.4.6/bin/easy_install -Z simplejson-2.0.9.tar.gz
sudo /usr/local/python2.4.6/bin/easy_install -Z unittest2-0.5.1.zip
sudo /usr/local/python2.4.6/bin/easy_install -Z mock-0.8.0.tar.gz
sudo find /usr/local/python2.4.6 -name '*.py[co]' -delete
tar jcvf ubuntu-python-2.4.6.tar.bz2 /usr/local/python2.4.6
