
"""
Example script to create a package info file for kicad-getlibs.


-make zip - name, ver
-get sha, size
-write .yml file


"""

import os
import yaml
import zipfile
import sys

common = os.path.abspath(os.path.join(sys.path[0], "..", 'kipi'))
if not common in sys.path:
    sys.path.append(common)

from checksum import get_sha256_hash

def write_package_file (filepath, data):
    with open(filepath, 'w') as outfile:
        yaml.dump(data, outfile, default_flow_style=False)

def zipdir(path, ziph):
    # ziph is zipfile handle
    for root, dirs, files in os.walk(path):
        for file in files:
            ziph.write(os.path.join(root, file))

def make_zip (folder, zip_name):
    zipf = zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED)
    zipdir(folder, zipf)
    zipf.close()

def make_version (name, version):
#
    zip_name = name + "-" + version + ".zip"

    if not os.path.exists (zip_name):
        make_zip (name, zip_name)

    zip_hash = get_sha256_hash (zip_name)

    content1 = {}
    content1 ['name'] = "footprint-wizard"
    content1 ['cache'] = "no"
    content1 ['url'] = "https://raw.githubusercontent.com/bobc/kicad-utils/v5/%s" % zip_name
    content1 ['checksum'] = "SHA-256:" + zip_hash
    content1 ['size'] = int(os.path.getsize(zip_name))
    content1 ['type'] = "script"
    content1 ['filter'] = name + "/footprint-wizards/*.*"

    package_version = {}
    package_version ['version'] = version
    package_version ['content'] = [content1]

    return package_version

#
#
#

package_name = "bobc-kicad-scripts"
publisher = "bobc"
description = "Footprint wizards"

versions = []
versions.append (make_version ("scripts", "1.0.0-rc1"))
versions.append (make_version ("scripts", "1.0.0-rc2"))
versions.append (make_version ("scripts", "1.0.0"))
versions.append (make_version ("scripts", "1.0.1"))

package = {}
package ['publisher'] = publisher
package ['description'] = description
package ['packages'] = versions

package_file = {}
package_file [package_name] = package

write_package_file ("%s.yml" % package_name, package_file)

print "package url:"
print "https://raw.githubusercontent.com/bobc/kicad-utils/v5/%s.yml" % package_name

