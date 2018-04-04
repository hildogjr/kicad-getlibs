
"""
Example script to create a package info file for kipi

"""

import argparse
import glob
import os
import sys
import zipfile

# needs pyyaml
import yaml

from checksum import get_sha256_hash

def after(value, a):
    # Find and validate first part.
    pos_a = value.find(a)
    if pos_a == -1: return ""
    # Returns chars after the found string.
    adjusted_pos_a = pos_a + len(a)
    if adjusted_pos_a >= len(value): return ""
    return value[adjusted_pos_a:]

def write_package_file (filepath, data):
    with open(filepath, 'w') as outfile:
        yaml.dump(data, outfile, default_flow_style=False)

def zipdir(path, ziph):
    # ziph is zipfile handle
    for root, dirs, files in os.walk(path):
        for file in files:
            ziph.write(os.path.join(root, file))

#
#
#

def make_zip (name, version, files):
    """make a zip from the specified files and version string"""

    if len(files) == 0:
        print ("No files found")
    else:
        print ("%d files found" % len(files))


        zip_name = name + "-" + version + ".zip"
        print ("Creating %s" % zip_name)
        zipf = zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED)
        #zipdir(folder, zipf)
        for file in files:
            zipf.write(file)
        zipf.close()

def get_files (path):

    # path = os.path.join (path, "*.*")
    files = []
    for filename in glob.glob(path):
        files.append (filename)

    return files
#
#
#

def make_version (zip_basename, version, zip_url, content_name, content_type, content_filter):
#
    zip_name = zip_basename + "-" + version + ".zip"

    if not os.path.exists (zip_name):
        print ("zip not found")

    zip_hash = get_sha256_hash (zip_name)

    content1 = {}
    content1 ['name'] = content_name
    #content1 ['cache'] = "no"
    content1 ['url'] = zip_url + zip_name
    content1 ['checksum'] = "SHA-256:" + zip_hash
    content1 ['size'] = int(os.path.getsize(zip_name))
    content1 ['type'] = content_type
    content1 ['filter'] = content_filter

    package_version = {}
    package_version ['version'] = version
    package_version ['content'] = [content1]

    return package_version

#
#
#
def gen_package(publisher, description, package_name, zip_name, zip_url, content_name, content_type, content_filter):
    """Create a package file including all zips found.

    Args:
        publisher: 
        description: 
        package_name:
        zip_name:
        zip_url:
        content_name:
        content_type:
        content_filter:

    Returns: 
        None
    """
    versions = []
    files = os.listdir (".")
    for file in files:
        if file.endswith (".zip"):
            vv = file.rsplit ('.',1)[0]
            vv = after(vv, "-")
            print ("Adding zip version %s" % vv)
            versions.append (make_version (zip_name, vv, zip_url, content_name, content_type, content_filter ))

    package = {}
    package ['publisher'] = publisher
    package ['description'] = description
    package ['packages'] = versions

    package_file = {}
    package_file [package_name] = package

    print ("Creating %s.yml" % package_name)
    write_package_file ("%s.yml" % package_name, package_file)


#
# Change the user_xxx functions according to your requirements.
#

def user_make_zip (version):
    """Make a zip stamped with latest version number"""

    if version== None:
        version = "0.1.0"

    # change to select files you need
    files = get_files ("scripts/footprint-wizards/*.py")
    make_zip ("scripts", version, files)

def user_make_package():
    """Make a package by scanning existing zip files"""

    # These are relevant if you are using github
    repo_owner = "bobc"
    repo_name = os.path.split (os.path.abspath(os.curdir))[-1]
    branch = "v5"

    # These are required for package generation
    publisher = "bobc"
    description = "Footprint wizards"
    package_name = "bobc-kicad-scripts"
    zip_name = "scripts"

    # Where the zips will be published, in this case use github
    zip_url = "https://raw.githubusercontent.com/%s/%s/%s/" % (repo_owner, repo_name, branch)

    content_name = "footprint-wizard"
    content_type = "script"
    # Optional, what files will be extracted from zip
    content_filter = zip_name + "/footprint-wizards/*.*"

    gen_package (publisher, description, package_name, zip_name, zip_url, content_name, content_type, content_filter)

    # where the package info might be published
    print ("")
    print ("Package url for github: https://raw.githubusercontent.com/%s/%s/%s/%s.yml" % (repo_owner, repo_name, branch, package_name))

#
#
#
if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="package creator for kipi")
    parser.add_argument("version",          help="specify a zip version", nargs="?")
    parser.add_argument("-z", "--zip",      help="create a zip file", action="store_true")
    parser.add_argument("-p", "--package",  help="generate the package info file", action="store_true")

    args = parser.parse_args()

    if args.zip:
        user_make_zip (args.version)

    elif args.package:
        user_make_package()

    else:
        parser.print_usage()
