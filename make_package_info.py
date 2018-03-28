
"""

make zip - name, ver

get sha, size

write .yml file

publisher
package
vers

zips...
   extracts...

"""

import os
import yaml
import zipfile
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

package_version1 = make_version ("scripts", "1.0.0")
#package_version2 = make_version ("scripts", "1.0.1")

versions = []
versions.append (package_version1)
#versions.append (package_version2)

# include previous versions?

package = {}
package ['publisher'] = publisher
package ['description'] = description
package ['packages'] = versions

package_file = {}
package_file [package_name] = package

write_package_file ("package_%s_info.yml" % package_name, package_file)

print "package url:"
print "https://raw.githubusercontent.com/bobc/kicad-utils/v5/package_%s_info.yml" % package_name

# https://raw.githubusercontent.com/akafugu/akafugu_core/master/package_akafugu_index.json
# "https://raw.githubusercontent.com/bobc/kicad-utils/v5/package_%s_info.yml" % package_name
# "https://raw.githubusercontent.com/bobc/kicad-utils/v5/%s" % zip_name
