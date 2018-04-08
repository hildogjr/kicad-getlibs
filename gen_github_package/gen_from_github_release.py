
"""
Create a package info file for kipi from github releases for a specified github
repository. This script uses the github API.

usage: gen_from_github_release <git user> <git repository name> [<content_types>]

e.g. gen_from_github_release bobc kicad-utils


"""

import argparse
import os
import sys
import zipfile
import requests
import json
import urllib
import tempfile

import yaml

common = os.path.abspath(os.path.join(sys.path[0], '../kipi'))
if not common in sys.path:
    sys.path.append(common)

from checksum import get_sha256_hash


def write_package_file (filepath, data):
    with open(filepath, 'w') as outfile:
        yaml.dump(data, outfile, default_flow_style=False)

def get_url(url, filename):
    try:
        print ("Getting %s to %s" % (url, filename))
        name, hdrs = urllib.urlretrieve(url, filename)
    except IOError, e:
        print ("error: Can't retrieve %r to %r: %s" % (url, filename, e))
        return False
    return True

def get_url_name (theurl):
    return theurl.rsplit ("/",1)[1]

def generate_info (git_user, git_repo, content_type):
    r = requests.get('https://api.github.com/repos/%s/%s' % (git_user, git_repo) )
    if r.ok:
        repoItem = json.loads(r.text or r.content)
        
        publisher = str(repoItem['owner']['login'])
        description = str(repoItem['description'])
        package_name = str(repoItem['name'])

        r = requests.get('https://api.github.com/repos/%s/%s/releases' % (git_user, git_repo))
        if r.ok:
            versions = []

            info = json.loads(r.text or r.content)

            if info:
                for release in info:

                    package_version = {}
                    package_version ['version'] = str(release['tag_name'])
                    package_version ['target'] = ["5"]
                    package_version ['content'] = []
                    versions.append (package_version)

                    #print release['assets']

                    for asset in release['assets']:
                        #print asset

                        content = {}
                        content ['name'] = str(asset['name']).rsplit(".", 1)[0]
                        content ['url'] = str(asset['browser_download_url'])
                        #content ['checksum'] = "SHA-256:" + zip_hash
                        content ['size'] = asset['size']
                        content ['type'] = content_type
                        content ['filter'] = "*/*"

                        #local_file = tempfile.mkstemp()
                        local_file = get_url_name (content ['url'])
                        if not os.path.exists (local_file):
                            get_url (content ['url'], local_file)
                        zip_hash = get_sha256_hash (local_file)
                        #os.unlink (local_file)

                        content ['checksum'] = "SHA-256:" + zip_hash

                        package_version ['content'].append (content)

                package = {}
                package ['publisher'] = publisher
                package ['description'] = description
                package ['packages'] = versions

                package_file = {}
                package_file [package_name] = package

                return package_file, package_name
            else:
                print "error: no releases found"
        else:
            print "error: unable to get release information"
    else:
        print "error: unable to get repository information"

    return None

#
#
#

parser = argparse.ArgumentParser(
    description="Create a package info file for kipi from github releases for a specified github repository.")

parser.add_argument("github_user", help="the github user name")
parser.add_argument("github_repo", help='the github repository name')
parser.add_argument("content_type", 
                    help='content types (footprint, symbol, 3dmodel, template, script). May be combined with ",". Default="footprint,symbol".', 
                    nargs='?', default="footprint,symbol")
#parser.add_argument("-v", "--verbose",  help="enable verbose output", action="store_true")
#parser.add_argument("-q", "--quiet",    help="suppress messages", action="store_true")
args = parser.parse_args()


info_file, package_name = generate_info (args.github_user, args.github_repo, args.content_type)

if info_file:
    write_package_file ("%s.yml" % package_name, info_file)

    print ("")
    print ("info file written to %s" % "%s.yml" % package_name)
    #print ("   package link would be: https://raw.githubusercontent.com/%s/%s/master/%s.yml" % (args.github_user, args.github_repo, package_name))
else:
    print "Errors found"
