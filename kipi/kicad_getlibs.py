#!/usr/bin/env python2
"""
@package
KiPI - A tool for downloading and installing KiCad packages, primarily for KiCad v5.

External dependencies: to clone git repos locally requires git, otherwise only zips can be used.

Runs on Windows, should run on Linux (MacOs might also work!).

Tested on Windows 7, 64 bit, not tested on other platforms.

Derived from https://github.com/hairymnstr/kicad-getlibs.
"""

from __future__ import print_function

import argparse
import glob
#import json
import os
from subprocess import Popen
import subprocess
import sys
import shutil
import urllib
#import urllib2
import zipfile

import yaml
import psutil

if __package__ is None:

    from __init__ import __version__

    from checksum import get_sha256_hash
    from str_util import *
    from lib_table import read_lib_table, write_lib_table
    from semver import Version, is_later_version

    import sexpdata
else:

    from .__init__ import __version__

    from .checksum import get_sha256_hash
    from .str_util import *
    from .lib_table import read_lib_table, write_lib_table
    from .semver import Version, is_later_version
    import sexpdata


class Paths():
    def __init__(self):
        self.kicad_config_dir=""

        self.ki_packages3d_dir=""
        self.ki_user_scripts_dir=""
        self.ki_user_templates_dir=""
        self.ki_portable_templates_dir=""

        self.cache_dir=""
        self.package_info_dir=""

        self.kipi_config_filename=""

        self.package_info_search_path=""

class PackageContent():
    def __init__(self):
        self.type = None
        self.name = ""
        self.url = ""
        self.checksum = ""
        self.size = 0
        self.filter = None

        # self.extracts=[]
        # type, filter

class PackageVersion():
    def __init__(self):
        self.version_str = ""
        self.contents = []

class PackageInfo():
    def __init__(self):
        self.name = ""
        self.publisher = ""
        self.description = ""
        self.versions = []

class PackageSet():
    def __init__(self):
        self.packages = []

#
# Platform dependent functions
#
def get_config_path (appname):

    if sys.platform == 'darwin':
        from AppKit import NSSearchPathForDirectoriesInDomains
        # http://developer.apple.com/DOCUMENTATION/Cocoa/Reference/Foundation/Miscellaneous/Foundation_Functions/Reference/reference.html#//apple_ref/c/func/NSSearchPathForDirectoriesInDomains
        # NSApplicationSupportDirectory = 14
        # NSUserDomainMask = 1
        # True for expanding the tilde into a fully qualified path
        appdata = os.path.join(NSSearchPathForDirectoriesInDomains(14, 1, True)[0], appname)
    elif sys.platform == 'win32':
        appdata = os.path.join(os.environ['APPDATA'], appname)
    else:
        # ~/.kicad
        appdata = os.path.expanduser(os.path.join("~", "." + appname))
    return appdata

def get_user_documents ():
    if sys.platform == 'darwin':
        user_documents = os.path.expanduser(os.path.join("~", "Documents"))
    elif sys.platform == 'win32':
        # e.g. c:\users\bob\Documents
        user_documents = os.path.join(os.environ['USERPROFILE'], "Documents")
    else:
        user_documents = os.path.expanduser(os.path.join("~", "Documents"))

    return user_documents


def get_running_processes (appname):
    processes = []
    for p in psutil.process_iter():
        try:
            if p.name().lower().startswith(appname):
                processes.append(p)
        except psutil.Error:
            pass

    return processes
#
# =============================================================================
#

def check_checksum(fname, checksum):

    actual_checksum = "SHA-256:" + get_sha256_hash(fname)

    if checksum != actual_checksum:
        print ("Error: bad hash, expected %s got %s" % (checksum, actual_checksum))
        return False

    return True

def make_folder (adir):
    if not os.path.exists(adir):
        try:
            os.makedirs(adir)
        except OSError:
            return False
    return True


def get_url(theurl, name):
    #try:
    #    name, hdrs = urllib.urlretrieve(theurl, name)
    #except IOError, e:
    #    print ("error: Can't retrieve %r to %r: %s" % (theurl, name, e))
    #    return False
    #return True

    try:
        # name, hdrs = urllib.urlretrieve(theurl, name)
        _opener = MyURLopener()
        _opener.retrieve(theurl, name)
        return True
    except IOError, e:
        if e.errno is None:
            s = ""
            for a in e:
                if isinstance(a, str):
                    s += a + " "
                elif isinstance(a, int):
                    s += str(a) + " "
            print ("error: can't get %r: %s" % (theurl, s))
        else:
            print ("error: Can't save to %r: IOError(%d) %s" % (name, e.errno, e.strerror ) )
        return False

def get_url_name (theurl):
    return theurl.rsplit ("/",1)[1]

class MyURLopener(urllib.FancyURLopener):
    def http_error_default(self, url, fp, errcode, errmsg, headers):
        # handle errors the way you'd like to
        urllib.URLopener.http_error_default (self, url, fp, errcode, errmsg, headers)

def get_unzipped(theurl, thedir, checksum):
    if not os.path.exists(thedir):
        os.makedirs(thedir)

    name = os.path.join(thedir, 'temp.zip')
    try:
        # name, hdrs = urllib.urlretrieve(theurl, name)
        _opener = MyURLopener()
        _opener.retrieve(theurl, name)
    except IOError, e:
        if e.errno is None:
            s = ""
            for a in e:
                if isinstance(a, str):
                    s += a + " "
                elif isinstance(a, int):
                    s += str(a) + " "
            print ("error: can't get %r: %s" % (theurl, s))
        else:
            print ("error: Can't save to %r: IOError(%d) %s" % (name, e.errno, e.strerror ) )
        return False

    #print ("downloaded %s" % name)

    new_name = theurl.rsplit ("/",1)[1]
    new_name = os.path.join (get_path (name), new_name)
    if os.path.exists(new_name):
        os.remove (new_name)
    os.rename (name, new_name)
    name = new_name

    # checksum
    if not check_checksum (name, checksum):
        #print ("Error: bad hash, expected %s got %s" % ( checksum, hash))
        return False
    #
    try:
        print ("Unzipping %s" % name)
        z = zipfile.ZipFile(name)
    except zipfile.error, e:
        print ("error: Bad zipfile (from %r): %s" % (theurl, e))
        return False
    z.extractall(thedir)
    z.close()
    return True




def get_zip (zip_url, target_path, checksum):

    zip_present = False

    if os.path.exists (target_path):
        zip_files = glob.glob (os.path.join (target_path, "*.zip"))
        if len(zip_files) > 0:
            zip_name = zip_files[0]
            if check_checksum (zip_name, checksum):
                zip_present = True

    if zip_present:
        print ("Already got " + target_path)
        return True
    else:
        if args.test:
            print ("Would get zip to %s " % target_path)
            return False
        else:
            print ("Getting zip from " + zip_url)
            return get_unzipped (zip_url, target_path, checksum)

def git_clone_or_update (repo_url, target_path, target_name, git_output):
  
    repo_name = repo_url.rsplit('/', 1)[1]
    #name = repo_name.rstrip(".git")

    # path = os.path.join (target_path, "..")
    # path = target_path

    if os.path.isdir(os.path.join(target_path, target_name)):
        if args.test:
            print ("Would update %s" % os.path.join(target_path, target_name))
        else:
            if not args.quiet:
                print ("Updating repo", repo_name)
            pr = Popen(["git", "pull"], cwd=os.path.join(target_path, target_name), stdout=git_output)
            pr.wait()
    else:
        if args.test:
            print ("Would clone repo %s to %s" % (repo_name, os.path.join(target_path, target_name) ))
        else:
            os.makedirs(target_path)

            cmd = ["git", "clone", repo_url, target_name]
            if not args.quiet:
                print ("Cloning repo", repo_name)
            if not args.verbose:
                # verbose mode
                cmd.append("-q")

            pr = Popen(cmd, cwd=target_path, stdout=git_output)
            pr.wait()


def get_git_status (git_path):

    # or iso-local
    cmd = ["git", "log", "-1", "--date=short"]

    p = Popen(cmd, shell=True, cwd=git_path, stdout=subprocess.PIPE)
    out, err = p.communicate()
    #print (p.returncode, out, err)
    lines = out.split('\n')

    s = after (lines[0], "commit ")[0:5] + " " + after (lines[2], "Date:").strip()
    return s

def get_git_branch_name (git_path):

    cmd = ["git", "status", "-sb"]

    p = Popen(cmd, shell=True, cwd=git_path, stdout=subprocess.PIPE)
    out, err = p.communicate()
    #print (p.returncode, out, err)
    lines = out.split('\n')

    s = after (lines[0], "## ")
    s = before (s, ".")
    return s

def get_git_branch_status (git_path, branch):

    cmd = ["git", "remote", "show", "origin"]

    p = Popen(cmd, shell=True, cwd=git_path, stdout=subprocess.PIPE)
    out, err = p.communicate()
    #print (p.returncode, out, err)
    lines = out.split('\n')

    s = ""
    for line in lines:
        tokens = line.strip().split()
        if "(" in line and tokens[0].startswith (branch):
            s = after (line, "(")
            s = before (s, ")")
            return s

    return s

def remove_table_entries (kicad_config_dir, table_type, publisher, package):

    changes = False

    table_name = table_type + "-lib-table"

    if table_type=="fp":
        ext = ".pretty"
    else:
        ext = ".lib"

    # purge entries
    if os.path.exists(os.path.join(kicad_config_dir, table_name)):
        libs = read_lib_table(os.path.join(kicad_config_dir, table_name), table_type)

        new_libs = []
        for lib in libs:
            remove = False

            if lib['options'].find("package=%s" % package) > -1:

                remove = True
                if publisher:
                    if lib['options'].find("publisher=%s" % publisher) > -1:
                        remove = True
                    else:
                        remove = False

            if remove:
                if args.verbose:
                    print ("remove: " + lib['name'])
                changes = True
            else:
                if args.verbose:
                    print ("keep  : " + lib['name'])
                new_libs.append(lib)

    if changes:
        save_table (kicad_config_dir, table_name, table_type, new_libs)

def update_global_table(kicad_config_dir, table_type, update_libs, package_path, publisher, package, version):

    changes = False

    table_name = table_type + "-lib-table"

    if table_type=="fp":
        ext = ".pretty"
    else:
        ext = ".lib"

    # first purge old entries
    if os.path.exists(os.path.join(kicad_config_dir, table_name)):
        libs = read_lib_table(os.path.join(kicad_config_dir, table_name), table_type)

        new_libs = []
        for lib in libs:
            if lib['options'].find("publisher=%s" % publisher) > -1:
                if args.verbose:
                    print ("remove: " + lib['name'])
                changes = True
            elif lib['uri'].find("github.com/KiCad") > -1 or lib['uri'].find("KIGITHUB") > -1 :
                # todo: KIGITHUB may not be KiCad
                # remove github/KiCad entries
                if args.verbose:
                    print ("remove: " + lib['name'])
                changes = True

            elif update_libs and update_libs.count (lib['name']+ext) > 0 :
                if args.verbose:
                    print ("remove: " + lib['name'])
                changes = True

            else:
                if args.verbose:
                    print ("keep  : " + lib['name'])
                new_libs.append(lib)

    elif not update_libs is None:
        print ("No %s found, creating from scratch" % table_name)
        new_libs = []
        
    if update_libs is None:
        pass
    else:
        # now add the new libs to the list
        for lib_name in update_libs:
            if lib_name.find(ext) > -1:
                lib = {}
                #lib['name'] = repo.rsplit('/', 1)[1].split(".")[0]
                lib['name'] = get_filename_without_extension(lib_name)
                if table_type == "fp":
                    lib['type'] = u'KiCad'
                else:
                    lib['type'] = u'Legacy'
                lib['uri'] = os.path.abspath(os.path.join(package_path, lib['name'] + ext))
                #lib['uri'] = "${KISYSMOD}/" + lib['name'] + ext
                lib['options'] = u'publisher=%s|package=%s|version=%s' % (publisher, package, version)
                lib['descr'] = u'""'

                if args.verbose:
                    print ("Insert: ", lib_name)
                new_libs.append(lib)
                changes = True

    # finally, save the new lib-table
    if changes:
        # todo : create numbered backup
        backup_name = table_name + "-old"
        if args.test:
            print ("Would create backup of %s to %s" % (table_name, os.path.join(kicad_config_dir, backup_name) ))
        else:
            if args.verbose:
                print ("Creating backup of %s to %s" % (table_name, os.path.join(kicad_config_dir, backup_name) ))
            shutil.copy2(os.path.join(kicad_config_dir, table_name), os.path.join(kicad_config_dir, backup_name))

        if args.test:
            print ("Would save %s to %s" % (table_name, os.path.join(kicad_config_dir, table_name) ))
        else:
            if args.verbose:
                print ("Saving %s to %s" % (table_name, os.path.join(kicad_config_dir, table_name) ))
            write_lib_table(os.path.join(kicad_config_dir, table_name), table_type, new_libs)

def save_table (kicad_config_dir, table_name, table_type, new_libs):
    # todo : create numbered backup
    backup_name = table_name + "-old"
    if args.test:
        print ("Would create backup of %s to %s" % (table_name, os.path.join(kicad_config_dir, backup_name) ))
    else:
        if args.verbose:
            print ("Creating backup of %s to %s" % (table_name, os.path.join(kicad_config_dir, backup_name) ))
        shutil.copy2(os.path.join(kicad_config_dir, table_name), os.path.join(kicad_config_dir, backup_name))

    if args.test:
        print ("Would save %s to %s" % (table_name, os.path.join(kicad_config_dir, table_name) ))
    else:
        if args.verbose:
            print ("Saving %s to %s" % (table_name, os.path.join(kicad_config_dir, table_name) ))
        write_lib_table(os.path.join(kicad_config_dir, table_name), table_type, new_libs)


def copy_3d_files (source_path, dest_path):

    files = []
    for root, dirnames, filenames in os.walk(source_path):
        for filename in filenames:
            if filename.endswith (".wrl") or filename.endswith (".step"):
                files.append (os.path.join (root, filename))

    copy_files (files, source_path, dest_path)



def recursive_copy_files(source_path, destination_path, overwrite=False):
    """
    Recursive copies files from source  to destination directory.
    :param source_path: source directory
    :param destination_path: destination directory
    :param overwrite if True all files will be overwritten otherwise skip if file exist
    :return: list of copied files and dirs
    """
    copied_files = []

    if not os.path.exists(destination_path):
        os.mkdir(destination_path)
    copied_files.append (destination_path)

    items = glob.glob(source_path + os.sep + '*')
    for item in items:
        if os.path.isdir(item):
            path = os.path.join(destination_path, item.split(os.sep)[-1])
            copied_files.extend ( recursive_copy_files(source_path=item, destination_path=path, overwrite=overwrite) )
        else:
            afile = os.path.join(destination_path, item.split(os.sep)[-1])
            if not os.path.exists(afile) or overwrite:

                if args.test:
                    print ("Would copy %s to %s" % (item, afile))
                else:
                    shutil.copyfile(item, afile)
                    copied_files.append (afile)

    return copied_files



def copy_files (files, source_path, dest_path):

    copied_files = []

    count = 0
    interval = len(files) / 10 + 1
    if not args.verbose:
        print ("Copying files..", end='')

    # todo: root folder?
    if not os.path.exists (dest_path):
        if args.test:
            print ("Would create %s " % dest_path)
        else:
            os.makedirs(dest_path)
            copied_files.append (dest_path)

    for filename in files:
        rel_path = os.path.relpath(filename, source_path)

        dest_file = os.path.join (dest_path, rel_path)
            
        adir = os.path.dirname (dest_file)
        if not os.path.exists (adir):
            if args.test:
                print ("Would create %s " % adir)
            else:
                os.makedirs(adir)
                copied_files.append (adir)

        if args.test:
            if count < 10:
                print ("Would create %s" % (dest_file))
            elif count == 10 and len(files) > 10:
                print ("Would copy %d others (omitted)" % (len(files)-10))
            
        else:
            if args.verbose:
                print ("copying %s to %s" % (filename, dest_file))
            shutil.copy2 (filename, dest_file)
            copied_files.append (dest_file)

            count += 1 
            if not args.verbose and (count % interval == 0):
                print ("%d%%.." % (count*100/len(files)), end='')

    if not args.verbose:
        print ("Done.")

    return copied_files

def copy_folders (folders, source_path, dest_path):

    copied_files = []

    # note: caller should create root folder
    if not os.path.exists (dest_path):
        if args.test:
            print ("Would create %s " % dest_path)
        else:
            os.makedirs(dest_path)

    count = 0
    interval = len(folders) / 10 + 1
    if not args.verbose:
        print ("Copying files..", end='')

    for folder in folders:
        rel_path = os.path.relpath(folder, source_path)
        #print ( rel_path)

        #dest = os.path.join (dest_path, folder[len(source_path)+1:])
        dest = os.path.join (dest_path, rel_path)

        #
        if args.verbose:
            print ("copy %s to %s" % (folder, dest))
        copied_files.extend(recursive_copy_files (folder, dest, True))

        count += 1 
        if not args.verbose and (count % interval==0):
            print ("%d%%.." % (count*100/len(folders)), end='')

    if not args.verbose:
        print ("Done.")

    return copied_files

def delete_files (files):
    if files is None:
        return

    for afile in files:
        if os.path.isdir (afile):
            pass
        else:
            if args.test:
                print ("would delete file %s" % (afile))
            else:
                if args.verbose:
                    print ("deleting %s" % (afile))

                try:
                    os.remove (afile)
                except OSError, e:
                    print ("error: can't delete file %s: %s" % (afile, e.strerror))

    files.reverse()
    for item in files:
        # only remove if empty?
        if os.path.isdir (item):
            if args.test:
                print ("would delete dir %s" % (item))
            else:
                f = os.listdir(item)
                if len(f) == 0:
                    if args.verbose:
                        print ("deleting %s" % (item))
                    try:
                        os.rmdir (item)
                    except OSError, e:
                        print ("error: can't delete directory %s: %s" % (item, e.strerror))
                else:
                    if args.verbose:
                        print ("%s is not empty" % (item))



def read_eeschema_config (path):
    with open(path) as f:
        config = f.read().split('\n')

    return config

def de_escape (s):
    result = ""
    in_escape = False
    for c in s:
        if in_escape:
            result += c
            in_escape = False
        else:
            if c== '\\':
                in_escape = True
            else:
                result += c

    return result

def update_bom_script_entry (paths):
    #
    # get from eeschema config

    config = read_eeschema_config (os.path.join(paths.kicad_config_dir, "eeschema"))

    bom_list_raw = [p for p in config if p.startswith ("bom_plugins")]

    if len(bom_list_raw)==1:
        bom_list_raw = after (bom_list_raw[0], "bom_plugins=")
        bom_list_raw = de_escape (bom_list_raw)
        bom_list = sexpdata.loads (bom_list_raw)

        for plugin in bom_list[1:]:
            print ("name = ", plugin[1].value())
            print ("cmd = " , plugin[2][1])

    # remove/add
    # xsltproc -o "%O.csv" "C:\Program Files\KiCad\bin\scripting\plugins\bom_cvs.xsl" "%I"

"""
footprint   (.pretty)
symbol      (.lib)
3dmodel     (.step, .wrl)
template    (folder containg .pro)
script      (.py)

worksheet file   (.wks)

bom script       (.py, .xsl)
footprint wizard (.py)
action plugin    (.py)
other script?    (.py)

demos (folder containing .pro)
tutorials?
language files?
"""

def change_extension (filename, ext):
    path, filename = os.path.split (filename)
    basename = os.path.splitext (filename)[0]
    return os.path.join (path, basename + ext)

def get_path (file_path):
    path, filename = os.path.split (file_path)
    return path

def get_filename (file_path):
    path, filename = os.path.split (file_path)
    return filename

def get_filename_without_extension (file_path):
    path, filename = os.path.split (file_path)
    basename = os.path.splitext (filename)[0]
    return basename

def is_writable (folder):
    if os.access(folder, os.W_OK | os.X_OK):
        try:
            filename = os.path.join (folder, "_temp.txt")
            f = open(filename, 'w' )
            f.close()
            os.remove(filename)
            return True
        except OSError as e:
            print (e)
            return False


def get_libs (target_path, file_spec, afilter, find_dirs):
    libs = []
    if afilter == "*/*":
        if find_dirs:
            for root, dirnames, filenames in os.walk(target_path):
                for dirname in dirnames:
                    if dirname.endswith (file_spec):
                        libs.append (os.path.join (root, dirname))
        else:
            for root, dirnames, filenames in os.walk(target_path):
                for filename in filenames:
                    if filename.endswith (file_spec):
                        libs.append (os.path.join(root,filename))

    else:
        if isinstance (afilter, basestring):
            afilter = [afilter]
        for f in afilter:
            f = f.strip()
            path = target_path + os.sep + f
            if (os.path.isdir(path)):
                path = os.path.join (path, "*.*")
            for filename in glob.glob(path):
                if filename.endswith (file_spec):
                    libs.append (filename)
    return libs

def uninstall_libraries (paths, atype, publisher, package_name):

    if atype is None or "footprint" in atype:
        remove_table_entries (paths.kicad_config_dir, "fp", publisher, package_name)

    if atype is None or "symbol" in atype:
        remove_table_entries(paths.kicad_config_dir, "sym", publisher, package_name)

def install_libraries (paths, target_path, atype, afilter, publisher, package_name, target_version):

    files = []

    if "footprint" in atype:
        # kicad_mod, other supported types
        libs = get_libs (target_path, ".pretty", afilter, True)

        if len(libs) > 0:
            print ("footprint libs: ", len(libs))

            update_global_table(paths.kicad_config_dir, "fp", libs, target_path, publisher, package_name, target_version)
        else:
            print ("No footprint libraries found in %s" % target_path)

    if "symbol" in atype:
        libs = get_libs (target_path, ".lib", afilter, False)
        # future: .sweet

        if len(libs) > 0:
            print ("Symbol libs: ", len(libs))
            update_global_table(paths.kicad_config_dir, "sym", libs, target_path, publisher, package_name, target_version)
        else:
            print ("No symbol libraries found in %s" % target_path)

    if "3dmodel" in atype:
        libs = get_libs (target_path, ".wrl", afilter, False)
        libs.extend (get_libs (target_path, ".step", afilter, False))
       
        # copy to ...

        if len(libs) > 0:
            print ("3D model files: ", len(libs))
            # 
            # make_folder (ki_packages3d_dir)
            ok = False
            if os.path.exists (paths.ki_packages3d_dir):
                if is_writable (paths.ki_packages3d_dir):
                    ok = True
                else:
                    print ("error: can't write to %s" % paths.ki_packages3d_dir)
            else:
                if make_folder (paths.ki_packages3d_dir):
                    ok = True
                else:
                    print ("error: can't create %s" % paths.ki_packages3d_dir)

            if ok:
                files = copy_files(libs, target_path, paths.ki_packages3d_dir)
        else:
            print ("No 3D Models found in %s" % target_path)

    if "template" in atype:
        # todo
        # could also check for 'meta' folder
        # also worksheet files?
        # copy to portable templates?
        libs = get_libs (target_path, ".pro", afilter, False)
        template_folders = []
        for lib in libs:
            path = get_path (lib)
            if args.verbose:
                print ("template %s" % path)
            template_folders.append (path)

        # copy to user templates

        if len(template_folders) > 0:
            print ("Templates: ", len(template_folders))
            make_folder (paths.ki_user_templates_dir)
            files = copy_folders (template_folders, target_path, paths.ki_user_templates_dir)
        else:
            print ("No templates found in %s" % target_path)

    if "script" in atype:
        # check for simple vs complex scripts?

        scripts = get_libs (target_path, ".py", afilter, False)

        if len(scripts) > 0:
            print ("Scripts : ", len(scripts))

            if isinstance (afilter, basestring):
                path = get_path (target_path + os.sep + afilter)
            else:
                path = target_path

            make_folder (paths.ki_user_scripts_dir)
            files = copy_files (scripts, path, paths.ki_user_scripts_dir)
        else:
            print ("No scripts found in %s" % target_path)

    if "bom-script" in atype:
        update_bom_script_config ()

    return files


def read_package_info (filepath):
    debug = False
    providers = []
    with open(filepath, 'r') as stream:
        try:
            parsed = yaml.load(stream)  # parse file

            if parsed is None:
                print("error: empty package file!")
                return

            for source in parsed:
                kwargs = parsed.get(source)

                # name is a reserved key
                if 'name' in kwargs:
                    print("error: name is already used for root name!")
                    continue
                kwargs['name'] = source

                providers.append (kwargs)

                for package in kwargs['packages']:
                    if debug: 
                        print ("   package: ver: %s" % ( package['version']))

                    for content in package['content']:
                        if debug: 
                            print ("      content: type: %s url: %s filters: %s" % ( 
                                content['type'], content['url'],
                                content['filter'] if "filter" in content else "*/*"
                                ))

            return providers
        except yaml.YAMLError as exc:
            print(exc)
            return None

def write_config (filepath, data):
    with open(filepath, 'w') as outfile:
        yaml.dump(data, outfile, default_flow_style=False)

def read_config (filepath):
    if os.path.exists (filepath):
        with open(filepath, 'r') as f:
            try:
                data = f.read()
                parsed = yaml.load(data)  # parse file

                if parsed is None:
                    print("error: empty config file!")
                    return parsed

                return parsed

            except yaml.YAMLError as exc:
                print (exc)
                return None
            except IOError:
                print("Unexpected error:", sys.exc_info()[0])
                return None
    else:
        return None


def git_check ():
    os.system('git version > tmp' )

    info = open('tmp', 'r').read()

    if info.startswith ("git version"):
        return True
    else:
        print ("Warning : git is not installed!")
        return False

def find_file (search_path, filename):
    for p in search_path:
        filepath = os.path.join (p, filename)
        if os.path.exists (filepath):
            return filepath
    return filename

def find_files (search_path, wildcard):
    files = []
    for p in search_path:
        files.extend (glob.glob (os.path.join(p,wildcard)))
    return files


def find_version (provider, target_version):
    # find matching version
    match_package = None
    match_version = Version()

    for package in provider['packages']:
        if target_version == "latest":
            if package['version'] == "latest":
                match_package = package
                break
            else:
                this_ver = Version (package['version'])
                if match_version is None or this_ver.compare (match_version):
                    match_package = package
                    match_version = Version(package['version'])
        elif package['version'] == target_version:
            match_package = package
            break

    return match_package


#
#
#

class Kipi():

    def __init__(self):

        self.paths = Paths()

        self.config=None
        self.git_output=None

        self.default_package_file=""
        self.package_file=""
        self.package_url=""

    def remove_installed (self, publisher, package_name):

        if "installed" in self.config:
            installed = self.config['installed']
            new_list = []
            for p in installed:
                if p['publisher']==publisher and p['package']==package_name:
                    delete_files (p['files'])
                else:
                    new_list.append (p)

            self.config['installed'] = new_list


    def add_installed (self, publisher, package_name, target_version, apackage_file, apackage_url, atypes, files, git_path):
        installed = None
        if "installed" in self.config:
            installed = self.config['installed']

        if installed is None:
            installed = []

        #todo: content types
        package = {}
        package['publisher'] = publisher
        package['package'] = package_name
        package['version'] = target_version
        package['package_file'] = apackage_file
        package['url'] = apackage_url
        package['type'] = atypes
        package['files'] = files
        package['git_repo'] = git_path

        new_list = []
        for p in installed:
            if p['publisher']==publisher and p['package']==package_name:
                pass
            else:
                new_list.append (p)

        new_list.append (package)
        self.config['installed'] = new_list

    def get_package_file(self, _package_file):

        if _package_file:
            if _package_file.startswith("http"):
                self.package_url = _package_file
                self.package_file = os.path.join (self.paths.package_info_dir, get_url_name (_package_file))
                self.package_file = change_extension (self.package_file, ".yml")
                make_folder (self.paths.package_info_dir)
                if not get_url (_package_file, self.package_file):
                    #print ("error retrieving %s" % _package_file)
                    return 1
            else:
                self.package_url = None
                if not _package_file.endswith (".yml"):
                    _package_file = change_extension (_package_file, ".yml")
                self.package_file = find_file ( self.paths.package_info_search_path, _package_file)
                
            if os.path.exists (self.package_file):
                providers = read_package_info (self.package_file)
            else:
                print ("error: can't open package file %s" % self.package_file)
                return 1

        elif os.path.exists (self.default_package_file):
            self.package_file = self.default_package_file 
            providers = read_package_info (self.default_package_file)
        else:
            print ("error: No package file specified")
            return 1

        if providers is None:
            print ("error: No package info found")
            return 1

        return 0

    def install (self, apackage_file, target_version, actions):
    
        providers = read_package_info (apackage_file)
        if providers is None:
            return 1

        if not target_version:
            target_version = "latest"

        changes = True
        self.config ['default_package'] = apackage_file

    #    if "download" in actions:
        for provider in providers:
            print ("Provider: %s, description: %s" % ( provider['name'], provider['description']))
    #
            # find matching version
            match_package = find_version (provider, target_version)
    #
            if match_package is None:
                print ("Error : version %s not found in %s" % (target_version, provider['name']))
                break
            #
            actual_version = match_package['version']

            package = match_package
            #for package in provider['packages']:
            #if package['version'] == target_version:
            # print ("   package: ver: %s" % ( package['version']))
                 
            for content in package['content']:
                #print "      content: type: %s url: %s filters: %s" % ( 
                #    content['type'], content['url'],
                #    content['filter'] if "filter" in content else "*/*"
                #    )

                target_path = os.path.join (self.paths.cache_dir, provider['publisher'], provider['name'], content['name'], actual_version)

                print ("Data source: %s" % (content['url']))

                if "download" in actions:
                    url = content['url']
                    if url.endswith(".git"):
                        git_path = os.path.join (self.paths.cache_dir, provider['publisher'], provider['name'], content['name'])
                        git_clone_or_update (url, git_path, actual_version, self.git_output)

                        git_path = os.path.join (git_path, actual_version)
                        ok = True
                    else:
                        # get zip
                        git_path = None
                        if "checksum" in content:
                            ok = get_zip (url, target_path, content['checksum'])
                        else:
                            print ("Error: missing checksum for %s" % content['name'])
                            ok = False

                    if ok and "install" in actions:
                        if "type" in content:
                            files = install_libraries (self.paths, target_path, 
                                                       content['type'], content['filter'] if "filter" in content else "*/*",
                                                       provider['publisher'], provider['name'], actual_version)

                            self.add_installed (provider['publisher'], provider['name'], package['version'], 
                                                apackage_file, self.package_url, content['type'],
                                                files, git_path)
                            changes = True

                        else:
                            for extract in content['extract']:
                                files = install_libraries (self.paths, target_path,
                                                           extract['type'], extract['filter'] if "filter" in extract else "*/*",
                                                           provider['publisher'], provider['name'], actual_version)

                                self.add_installed (provider['publisher'], provider['name'], package['version'], 
                                                    apackage_file, self.package_url, extract['type'],
                                                    files, git_path)
                                changes = True

                #elif "remove" in actions:
                #    if "type" in content:
                #        uninstall_libraries (self.paths, target_path, content['type'],
                #                                content['filter'] if "filter" in content else "*/*",
                #                                provider['publisher'], provider['name'], actual_version)

                #        self.remove_installed (provider['publisher'], provider['name'], actual_version)
                #        changes = True

                #    else:
                #        for extract in content['extract']:
                #            uninstall_libraries (self.paths, target_path,
                #                                extract['type'],
                #                                extract['filter'] if "filter" in extract else "*/*",
                #                                provider['publisher'], provider['name'], actual_version)

                #            self.remove_installed (provider['publisher'], provider['name'], actual_version)
                #            changes = True

            print ("")
        # for

        if changes and not args.test:
            write_config (self.paths.kipi_config_filename, self.config)

        return 0

    def remove (self, publisher, package_name):
        temp = [p for p in self.config['installed'] if p['package'] == package_name]

        if publisher:
            packages = [p for p in temp if p['publisher'] == publisher]
        else:
            packages = temp

        changes = False
        if len(packages) == 1:
            # todo: get type?
            uninstall_libraries (self.paths, None, packages[0]['publisher'], package_name)

            self.remove_installed (packages[0]['publisher'], package_name)
            changes = True
    
            if changes and not args.test:
                write_config (self.paths.kipi_config_filename, self.config)
           
            return 0    
        elif len(packages) > 1:
            print ("error: package name %s is ambiguous" % package_name)
            return 2
        else:
            print ("error: package name %s not installed" % package_name)
            return 2

    def test(self):
        update_bom_script_entry (self.paths)


    def run(self):

        # default is to dump git output to null, i.e. not verbose
        self.git_output = open(os.devnull, "w")
        absolute = True
        actions = ""

        if args.verbose:
            self.git_output.close()
            self.git_output = None

        #if args.config:
        #    actions = "configure"

        if args.download:
            actions = "download"

        if args.install:
            actions = "download,install"

        if args.remove:
            actions = "remove"

        if args.update:
            actions = "update"

        #
        kipi_config_folder = get_config_path("kipi")
        self.paths.kipi_config_filename = os.path.join (kipi_config_folder, "kipi.cfg")

        if os.path.exists(self.paths.kipi_config_filename):
            self.config = read_config (self.paths.kipi_config_filename)
        else:
            self.config = None

        if args.config:
            if self.config is None:
                self.config = {}
                self.config ['default_package'] = "kicad-official-libraries-v5.yml"
            self.config ['cache_path'] = args.config # todo check/default?
            make_folder (kipi_config_folder)
            write_config (self.paths.kipi_config_filename, self.config)
            return 0

        if not self.config:
            print ("error: need configuration")
            print ("run kipi -c <cache_path>")
            return 1


        self.paths.cache_dir = self.config['cache_path']
        self.default_package_file = self.config ['default_package']

        self.paths.package_info_dir = os.path.join (self.paths.cache_dir, "packages")

        self.paths.package_info_search_path = [".", self.paths.package_info_dir, "../packages"]

        user_documents = get_user_documents()
        self.paths.kicad_config_dir = get_config_path("kicad")

        self.paths.ki_packages3d_dir = os.environ['KISYS3DMOD']
        # also system templates?
        self.paths.ki_user_templates_dir = os.path.join(user_documents, "kicad", "template")
        self.paths.ki_portable_templates_dir = os.environ['KICAD_PTEMPLATES']

        self.paths.ki_user_scripts_dir = os.path.join(self.paths.kicad_config_dir, "scripting")

        #C:\Users\bob\AppData\Roaming\kicad\scripting
        #C:\Users\bob\AppData\Roaming\kicad\scripting\plugins

        # ~/.kicad_plugins/
        # C:\Users\bob\AppData\Roaming \kicad \scripts

        #
        #self.test()

        #
        have_git = git_check()

        if (args.install or args.update or args.remove) and get_running_processes("kicad"):
            print ("error: cannot modify installed packages while kicad is running")
            return 2

        if args.update:
            if "installed" in self.config and self.config['installed']:
                update_packages = []
                for package in self.config['installed']:
                    # get from url?
                    # only if flag?
                    if package['url']:
                        self.get_package_file (package['url'])

                    #
                    providers = read_package_info (package['package_file'])
                    if providers:
                        latest_package = find_version (providers[0], "latest")

                    latest = Version (latest_package['version'])
                    if latest.compare (Version (package['version'])):
                        print ("%-15s %-20s %s (latest %s)" % (package['publisher'], package['package'], package['version'],
                                                              latest_package['version'] if latest_package else "") )
                        update_packages.append(package)

                if len(update_packages) > 0:
                    ans = raw_input( "Update packages [Y] ? ")
                    if ans == "" or ans.lower().startswith("y"):
                    #
                        for package in update_packages:
                            # remove current?
                            # remove_package (package)

                            self.package_url = package['url']
                            self.remove (package['package_file'], package['version'])

                            self.install (package['package_file'], latest_package['version'], "download,install")

                else:
                    print ("No updates available")
            else:
                print ("no packages installed")
            err_code = 0

        elif args.catalog:
            # 
            files = find_files (self.paths.package_info_search_path, "*.yml")

            print ("Local package info files:")
            print ("")

            if files:
                for f in files:
                    print ("  " + f)
            else:
                print ("No local package info files found")
            err_code = 0

        elif args.list:
            if "installed" in self.config and self.config['installed']:
                print ("%-15s %-35s %-28s %s" % ("Publisher", "Package name", "Installed Version (latest)", "Source") )
                print ('-' * (15+1+35+1+28+1+10))
                for package in self.config['installed']:
                    # get from url?
                    # only if flag?
                    if package['url']:
                        self.get_package_file (package['url'])

                    #
                    providers = read_package_info (package['package_file'])
                    if providers:
                        # TODO 
                        latest_package = find_version (providers[0], "latest")

                    s = "%-15s %-35s" % (package['publisher'], package['package']) 
            
                    if package['version'] == "latest":
                        if "git_repo" in package:
                            s += " git: %s" % get_git_status (package['git_repo'])

                            branch = get_git_branch_name (package['git_repo'])
                            status = get_git_branch_status (package['git_repo'], branch)
                            if s:
                                s += " (%s)" % status
                        else:
                            s += " git: unknown"
                    else:
                        ver = package['version']
                        if latest_package and is_later_version (latest_package['version'], package ['version']):
                            ver += " (latest %s)" % latest_package['version']
                        s += " %-28s" % ver

                    if package['url']:
                        s += " %s" % package['url']
                    elif "file" in package and package['file']:
                        s += " %s" % package['file']

                    print (s)

                    if args.verbose:
                        if package['files']:
                            for f in package['files']:
                                print ("   %s" % (f))

            else:
                print ("no packages installed")
            err_code = 0

        elif args.download or args.install:
            err_code = self.get_package_file(args.package_spec)

            #todo: may need to remove first
            if err_code == 0:
                err_code = self.install(self.package_file, args.version, actions)

        elif args.remove:


            # remove any installed packages in pack_file
            # by publisher, name?
            err_code = self.remove(None, args.package_spec)

        else:
            # print help
            err_code = 101

        return err_code

#
# main
#

args = None

def main():
    global args

    parser = argparse.ArgumentParser(description="Download and install KiCad data packages")

    parser.add_argument("package_spec",     help="specifies the package to download/install", nargs='?')
    parser.add_argument("version",          help='a valid version from the package file or "latest"', nargs='?')

    parser.add_argument("-v", "--verbose",  help="enable verbose output", action="store_true")
    parser.add_argument("-q", "--quiet",    help="suppress messages", action="store_true")
    parser.add_argument("-t", "--test",     help="dry run", action="store_true")

    #
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config",  metavar="local_folder", help="configure get-libs. <local_folder> is the folder which stores downloaded package data")
    group.add_argument("--download", help="download the specified package data", action="store_true")
    group.add_argument("--install",  help="install package data into KiCad (implies download)", action="store_true")
    group.add_argument("--remove" ,  help="remove an installed package from KiCad", action="store_true")
    group.add_argument("--update" ,  help="update packages installed in KiCad", action="store_true")
    group.add_argument("--list",     help="list installed packages", action="store_true")

    group.add_argument("--catalog",  help="list local package files", action="store_true")
    group.add_argument("--version",  action="version", version='KiPI ' + __version__)

    #

    args = parser.parse_args()

    installer = Kipi()

    err_code = installer.run ()

    if err_code == 101:
        parser.print_help()
        err_code = 0

    sys.exit(err_code)

# main entrypoint.
if __name__ == '__main__':
    main()
