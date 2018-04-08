#!/usr/bin/env python2
# -*- coding: ascii -*- 
"""
module - short description

long descruption

Usage

Authors

License

Copyright Bob Cousins 2018

"""

__author__ = 'Bob Cousins' 
__copyright__ = 'Copyright 2018 Bob Cousins' 
__license__ = 'GPL 3.0' 
__version__ = '0.1.0'


#imports
import argparse
import os
import glob
import sys

common = os.path.abspath(os.path.join(sys.path[0], '../kipi'))
if not common in sys.path:
    sys.path.append(common)
from kicad_getlibs import read_package_info


class PackageFile:

    def __init__(self):
        self.init = True

    def read (self, filename):
        self.info = read_package_info (filename)
        self.filename = filename

def write_md (index, filename, url_base):

    outf = open (filename, "w")

    outf.write ("""
Package Index
=============

""")

    for pub in index:

        outf.write ("* Publisher: %s\n" % pub )

        for pf in index[pub]:
            # print pf.filename
            for p in pf.info:
                ver = ""
                if 'target' in p:
                    for v in p['target']:
                        if ver:
                            ver += ','
                        ver += "v"+str(v)

                outf.write ("  * Description: %s" % p['description'])
                if ver:
                    outf.write (" (KiCad %s)" % ver)
                outf.write ("\n")

                outf.write ("    * URL: %s%s\n" % (url_base, os.path.split(pf.filename)[1] ) )
                outf.write ("\n")

def main():
    global args

    parser = argparse.ArgumentParser(description="Generate package index")
    parser.add_argument("filename",     help="name of output index file")
#    parser.add_argument("-v", "--verbose",  help="enable verbose output", action="store_true")
    args = parser.parse_args()

    files = []

    files = glob.glob ("C:\\git_bobc\\kicad-getlibs\\packages\\*.yml")

    #publisher, package
    packages = []

    for f in files:
        info = PackageFile ()
        info.read(f)
        packages.append (info)

    publishers = []
    for pf in packages:
        for p in pf.info:
            if not p['publisher'] in publishers:
                publishers.append(p['publisher'])

    publishers.sort(key=lambda x : x.upper())

    index = {}
    for pub in publishers:
        publisher_list = []
    
        for pf in packages:
            for p in pf.info:
                if p['publisher'] == pub:
                    publisher_list.append(pf)

        index [pub] = publisher_list


    url_base = "https://raw.githubusercontent.com/bobc/kicad-getlibs/master/packages/"

    write_md (index, args.filename, url_base)


# main entrypoint.
if __name__ == '__main__':
    main()

