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
import copy
import glob
#import json
import os
from subprocess import Popen
import subprocess
import sys
import shutil
import time
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
    from sexpdata import Symbol

    import sexpdata
else:

    from .__init__ import __version__

    from .checksum import get_sha256_hash
    from .str_util import *
    from .lib_table import read_lib_table, write_lib_table
    from .semver import Version, is_later_version
    from .sexpdata import Symbol

    import sexpdata

#
#
#
valid_content_types = ["footprint", "symbol", "3dmodel", "template", "script", "bom-plugin"]


#
#
#
class Paths():
    def __init__(self):
        # KiCad paths
        self.kicad_config_dir=""

        # from KISYS3DMOD
        self.ki_packages3d_dir=None
        self.ki_user_scripts_dir=""
        self.ki_user_templates_dir=""
        # from KICAD_PTEMPLATES
        self.ki_portable_templates_dir=None

        # aka KIGITHUB
        self.ki_github_url = None

        # kipi paths
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
        self.kicad_targets = []  # kicad versions supported
        self.versions = []

class PackageSet():
    def __init__(self):
        self.packages = [] # of PackageInfo

class Path ():

    def __init__(self, s = None):
        if s:
            self.assign (s)
        else:
            self.parts = []
            self.filespec = None
            self.recurse = False

    def assign (self, s):
        self.parts = s.split("/")

        last = self.parts[-1] if len(self.parts)>0 else None

        self.filespec = None
        self.recurse = False

        if last == "":
            self.parts = self.parts[:-1]
            last = self.parts[-1] if len(self.parts)>0 else None
        
        if last == '*' or last=='*.*' or ('.' in last and last != '...'):
            self.filespec = last

            self.parts = self.parts[:-1]
            last = self.parts[-1] if len(self.parts)>0 else None

        if last == "...":
            self.recurse = True
            self.parts = self.parts[:-1]

    def get_path (self, path):
        result = os.path.join (path, os.sep.join (self.parts))
        if self.filespec:
            result = os.path.join (result, self.filespec)
        return result

    def __str__ (self):
        s = os.sep.join (self.parts) + ' _ ' 
        if self.recurse:
            s += '...' 
        s += ' _ '
        if self.filespec:
            s += self.filespec
        return s

    __repr__ = __str__

#
# Platform dependent functions
#
def get_app_config_path (appname):

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
    if not os.path.isdir(adir):
        try:
            os.makedirs(adir)
        except OSError as ex:
            print ("error creating %s: %s" % (adir, ex.strerror))
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
    if not make_folder (thedir):
        return False

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
    return unzip_zip (thedir, name)


def unzip_zip(thedir, name):
    try:
        print ("Unzipping %s" % name)
        z = zipfile.ZipFile(name)
    except zipfile.error, e:
        print ("error: Bad zipfile: %s" % (e))
        return False

    #z.extractall(thedir)
    for f in z.infolist():
        name, date_time = f.filename, f.date_time
        name = os.path.join(thedir, name)
        if name.endswith('\\') or name.endswith('/'):
            make_folder (name)
        else:
            with open(name, 'wb') as outFile:
                outFile.write(z.open(f).read())
            date_time = time.mktime(date_time + (0, 0, -1))
            os.utime(name, (date_time, date_time))

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
        # check if zip expanded?

        files = os.listdir(target_path)
        if len(files)==1:
            # unzip
            return unzip_zip (target_path, zip_name)

        return True
    else:
        if args.test:
            print ("Would get zip to %s " % target_path)
            return False
        else:
            print ("Getting zip from " + zip_url)
            return get_unzipped (zip_url, target_path, checksum)

#
# functions calling external git
#
def git_check ():
    cmd = ["git", "version"]

    p = Popen(cmd, shell=True, stdout=subprocess.PIPE)
    out, err = p.communicate()
    #print (p.returncode, out, err)
    lines = out.split('\n')

    if out.startswith ("git version"):
        return True
    else:
        # print ("Warning : git is not installed!")
        return False


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
            #pr = Popen(["git", "pull", "--depth=1"], cwd=os.path.join(target_path, target_name), stdout=git_output)
            pr = Popen(["git", "pull"], cwd=os.path.join(target_path, target_name), stdout=git_output)
            pr.wait()
    else:
        if args.test:
            print ("Would clone repo %s to %s" % (repo_name, os.path.join(target_path, target_name) ))
        else:
            make_folder(target_path)

            cmd = ["git", "clone", "--depth=1", repo_url, target_name]
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

#
#
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

def update_global_table(kicad_config_dir, table_type, update_libs, publisher, package, version):

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
            # todo: 
            # remove by publisher
            if lib['options'].find("publisher=%s" % publisher) > -1:
                if args.verbose:
                    print ("remove: " + lib['name'])
                changes = True

            # remove if KiCad??
            elif lib['uri'].find("github.com/KiCad") > -1 or lib['uri'].find("KIGITHUB") > -1 :
                # todo: KIGITHUB may not be KiCad
                # remove github/KiCad entries
                if args.verbose:
                    print ("remove: " + lib['name'])
                changes = True

            # remove if going to replace
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
                # todo: other types
                if table_type == "fp":
                    lib['type'] = u'KiCad'
                else:
                    lib['type'] = u'Legacy'
                lib['uri'] = lib_name
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



def copy_files (source_path, files, dest_path, existing_files):

    copied_files = []

    #
    if existing_files:
        for filename in existing_files:
            rel_path = os.path.relpath(filename, dest_path)

            if not os.path.join (source_path, rel_path) in files:
                if os.path.isfile (filename):
                    delete_file (filename)
    #

    count = 0
    interval = len(files) / 10 + 1
    if not args.verbose:
        print ("Copying files..", end='')

    # todo: root folder?
    if not os.path.isdir (dest_path):
        if args.test:
            print ("Would create %s " % dest_path)
        else:
            make_folder(dest_path)
            copied_files.append (dest_path)

    for filename in files:
        rel_path = os.path.relpath(filename, source_path)

        dest_file = os.path.join (dest_path, rel_path)
        
        # create new folder if necessary
        dest_dir = os.path.dirname (dest_file)
        if not os.path.isdir (dest_dir):
            if args.test:
                print ("Would create %s " % dest_dir)
            else:
                make_folder(dest_dir)
                copied_files.append (dest_dir)

        copy_file = False
        if os.path.exists (dest_file):
            # is it different?
            if os.path.getsize(filename) != os.path.getsize(dest_file) or os.path.getmtime(filename) != os.path.getmtime(dest_file):
                copy_file = True
        else:
            # new file
            copy_file = True

        if copy_file:
            # copy the file
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

def copy_files2 (source_path, files, dest_path, dest_names, existing_files):

    copied_files = []

    #
    if existing_files:
        for filename in existing_files:
            rel_path = os.path.relpath(filename, dest_path)

            if not os.path.join (source_path, rel_path) in files:
                if os.path.isfile (filename):
                    delete_file (filename)
    #

    count = 0
    interval = len(files) / 10 + 1
    if not args.verbose:
        print ("Copying files..", end='')

    # todo: root folder?
    if not os.path.isdir (dest_path):
        if args.test:
            print ("Would create %s " % dest_path)
        else:
            make_folder(dest_path)
            copied_files.append (dest_path)

    j = 0
    for filename in files:
        if dest_names:
            rel_path = dest_names[j]
        else:
            rel_path = os.path.relpath(filename, source_path)
        j += 1

        dest_file = os.path.join (dest_path, rel_path)
        
        # create new folder if necessary
        dest_dir = os.path.dirname (dest_file)
        if not os.path.isdir (dest_dir):
            if args.test:
                print ("Would create %s " % dest_dir)
            else:
                make_folder(dest_dir)
                copied_files.append (dest_dir)

        copy_file = False
        if os.path.exists (dest_file):
            # is it different?
            if os.path.getsize(filename) != os.path.getsize(dest_file) or os.path.getmtime(filename) != os.path.getmtime(dest_file):
                copy_file = True
        else:
            # new file
            copy_file = True

        if copy_file:
            # copy the file
            if args.test:
                if count < 10:
                    print ("Would create %s" % (dest_file))
                elif count == 10 and len(files) > 10:
                    print ("Would copy %d others (omitted)" % (len(files)-10))
            
            else:
                if args.verbose:
                    print ("copying %s to %s" % (filename, dest_file))
                shutil.copy2 (filename, dest_file)

                count += 1 
                if not args.verbose and (count % interval == 0):
                    print ("%d%%.." % (count*100/len(files)), end='')

        if not args.test:
            copied_files.append (dest_file)

    if not args.verbose:
        print ("Done.")

    return copied_files

def copy_folders (folders, source_path, dest_path):

    copied_files = []

    # note: caller should create root folder
    if not os.path.isdir (dest_path):
        if args.test:
            print ("Would create %s " % dest_path)
        else:
            make_folder(dest_path)

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

def delete_file (afile):
    if args.test:
        print ("would delete file %s" % (afile))
    else:
        if args.verbose:
            print ("deleting %s" % (afile))
        try:
            os.remove (afile)
        except OSError, e:
            print ("error: can't delete file %s: %s" % (afile, e.strerror))

def delete_files (files):
    if files is None:
        return

    for afile in files:
        if os.path.isdir (afile):
            pass
        else:
            delete_file (afile)

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



def read_config_file (path):
    with open(path) as f:
        config = f.read().split('\n')

    return config

def write_config_file (path, config):
    with open(path, "w") as f:
        f.write('\n'.join(config))

def get_config_item (config, key):
    for p in config:
        if before(p,'=').strip() == key:
            return after(p, '=')

def update_config_file (config, key, value):
    new_config = []
    for p in config:
        if before(p,'=') == key:
            new_config.append (key + '=' + value)
        else:
            new_config.append(p)
    return new_config
    

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

def escape (s):
    result = ""
    for c in s:
        if c == '\\':
            result += '\\' + c
        else:
            result += c

    return result

def remove_bom_plugin_entry (paths, name):
    # get list of current plugins from eeschema config
    config = read_config_file (os.path.join(paths.kicad_config_dir, "eeschema"))
    bom_plugins_raw = [p for p in config if p.startswith ("bom_plugins")]

    new_list = []
    new_list.append (Symbol("plugins"))
    changes = False

    if len(bom_plugins_raw) == 1:
        bom_plugins_raw = after (bom_plugins_raw[0], "bom_plugins=")
        bom_plugins_raw = de_escape (bom_plugins_raw)

        # print (bom_plugins_raw)
        bom_list = sexpdata.loads (bom_plugins_raw)

        for plugin in bom_list[1:]:
            #print ("name = ", plugin[1].value())
            #print ("cmd = " , plugin[2][1])
            if plugin[1].value() == name:
                # we want to delete this entry
                if args.verbose:
                    print ("Removing %s" % name)
                changes = True
            else:
                new_list.append (plugin)

    if changes and not args.test:
        s = sexpdata.dumps (new_list)
        # save into config
        config = update_config_file (config, "bom_plugins", escape(s))
        write_config_file (os.path.join(paths.kicad_config_dir, "eeschema"), config)

# xsltproc -o "%O.csv" "C:\Program Files\KiCad\bin\scripting\plugins\bom_cvs.xsl" "%I"

def add_bom_plugin_entry (paths, name, cmd):
    # get from eeschema config
    config = read_config_file (os.path.join(paths.kicad_config_dir, "eeschema"))
    bom_plugins_raw = [p for p in config if p.startswith ("bom_plugins")]

    new_list = []
    new_list.append (Symbol("plugins"))

    if len(bom_plugins_raw)==1:
        bom_plugins_raw = after (bom_plugins_raw[0], "bom_plugins=")
        bom_plugins_raw = de_escape (bom_plugins_raw)

        #print (bom_plugins_raw)
        bom_list = sexpdata.loads (bom_plugins_raw)

        for plugin in bom_list[1:]:
            #print ("name = ", plugin[1].value())
            #print ("cmd = " , plugin[2][1])
            new_list.append (plugin)

    if not args.test:
        if args.verbose:
            print ("Adding %s" % name)
        new_list.append([Symbol('plugin'), Symbol(name), [Symbol('cmd'), cmd]])
        s = sexpdata.dumps (new_list)

        # save into config
        config = update_config_file (config, "bom_plugins", escape(s))
        write_config_file (os.path.join(paths.kicad_config_dir, "eeschema"), config)

"""
footprint   (.pretty)
symbol      (.lib)
3dmodel     (.step, .wrl)
template    (folder containg .pro)
script      (.py)

worksheet file   (.wks)

bom plugin (eeschema)  (.py, .xsl)
netlist plugin (eeschema)  (.py, .xsl)

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
    source_names = []
    dest_names = []

    if afilter == "*/*":
        if find_dirs:
            for root, dirnames, filenames in os.walk(target_path):
                for dirname in dirnames:
                    if dirname.endswith (file_spec):
                        source_name = os.path.join (root, dirname)
                        source_names.append (source_name)
                        rel_path = os.path.relpath(root, target_path)
                        dest_names.append (os.path.join (rel_path, dirname))
        else:
            for root, dirnames, filenames in os.walk(target_path):
                for filename in filenames:
                    if file_spec == '*.*' or filename.endswith (file_spec):
                        source_names.append (os.path.join(root,filename))
                        rel_path = os.path.relpath(root, target_path)
                        dest_names.append (os.path.join(rel_path, filename))

    else:
        if isinstance (afilter, basestring):
            afilter = [afilter]

        for f in afilter:
            f = f.strip()

            p = Path(f)
            #print (f + " => " + str(p))
            #path = target_path + os.sep + f

            path = p.get_path (target_path)

            if (os.path.isdir(path)):
                path = os.path.join (path, "*.*")

            if p.recurse:
                for root, dirnames, filenames in os.walk(p.get_path (target_path)):
                    for filename in filenames:
                        if file_spec == '*.*' or filename.endswith (file_spec):
                            source_names.append (os.path.join(root,filename))

                            rel_path = os.path.relpath(root, p.get_path (target_path))
                            dest_names.append (os.path.join(rel_path, filename))

            else:
                for filename in glob.glob(path):
                    if filename.endswith (file_spec):
                        source_names.append (filename)

                        rel_path = p.get_path (target_path)
                        dest_names.append (os.path.join(rel_path, filename))

    return source_names, dest_names

def uninstall_content (paths, publisher, package_name, content=None):

    atype = None
    if content and 'type' in content:
        atype = content['type']

    if atype is None or "footprint" in atype:
        remove_table_entries (paths.kicad_config_dir, "fp", publisher, package_name)

    if atype is None or "symbol" in atype:
        remove_table_entries(paths.kicad_config_dir, "sym", publisher, package_name)

    #todo:
    if atype is not None and "bom-plugin" in atype:
        remove_bom_plugin_entry (paths, package_name)

def install_content (paths, target_path, atype, afilter, publisher, package_name, target_version, content, existing_content=None):

    files = []
    existing_files = existing_content['files'] if existing_content and 'files' in existing_content else None

    if "footprint" in atype:
        # kicad_mod, other supported types
        libs, dest_names = get_libs (target_path, ".pretty", afilter, True)

        if len(libs) > 0:
            print ("Installing footprint libraries: ", len(libs))
            update_global_table(paths.kicad_config_dir, "fp", libs, publisher, package_name, target_version)
        else:
            print ("No footprint libraries found in %s" % target_path)

    if "symbol" in atype:
        libs, dest_names = get_libs (target_path, ".lib", afilter, False)
        # future: .sweet

        if len(libs) > 0:
            print ("Installing symbol libraries: ", len(libs))
            update_global_table(paths.kicad_config_dir, "sym", libs,  publisher, package_name, target_version)
        else:
            print ("No symbol libraries found in %s" % target_path)

    if "3dmodel" in atype:
        libs, dest_names = get_libs (target_path, ".wrl", afilter, False)

        result = get_libs (target_path, ".step", afilter, False)
        libs.extend (result[0])
        dest_names.extend(result[1])

        result = get_libs (target_path, ".stp", afilter, False)
        libs.extend (result[0])
        dest_names.extend(result[1])
       
        # copy to ...

        if len(libs) > 0:
            print ("Installing 3D model files: ", len(libs))
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
                files = copy_files2(target_path, libs, paths.ki_packages3d_dir, dest_names, existing_files)
        else:
            print ("No 3D Models found in %s" % target_path)

    if "template" in atype:
        # todo
        # could also check for 'meta' folder
        # also worksheet files?
        # copy to portable templates?
        libs, dest_names = get_libs (target_path, ".pro", afilter, False)
        
        template_folders = []
        for lib in libs:
            path = get_path (lib)
            if args.verbose:
                print ("template %s" % path)
            template_folders.append (path)

        # copy to user templates

        if len(template_folders) > 0:
            print ("Installing templates: ", len(template_folders))
            make_folder (paths.ki_user_templates_dir)
            files = copy_folders (template_folders, target_path, paths.ki_user_templates_dir)
        else:
            print ("No templates found in %s" % target_path)

    if "script" in atype:
        # check for simple vs complex scripts?
        # non-python scripts?

        scripts, dest_names = get_libs (target_path, ".py", afilter, False)

        if len(scripts) > 0:
            print ("Installing script files : ", len(scripts))

            if isinstance (afilter, basestring) and afilter != "*/*":
                path = get_path (target_path + os.sep + afilter)
            else:
                path = target_path

            make_folder (paths.ki_user_scripts_dir)
            files = copy_files (path, scripts, paths.ki_user_scripts_dir, existing_files)
        else:
            print ("No scripts found in %s" % target_path)

    if "bom-plugin" in atype:
        scripts, dest_names = get_libs (target_path, "*.*", afilter, False)
        
        scripts = [p for p in scripts if not p.endswith(".zip")]

        # remove_bom_plugin_entry () ?

        if len(scripts) > 0:
            print ("Installing BOM Plugin files : ", len(scripts))

            if isinstance (afilter, basestring) and afilter != "*/*":
                path = get_path (target_path + os.sep + afilter)
            else:
                path = target_path

            make_folder (paths.ki_user_scripts_dir)
            files = copy_files (path, scripts, paths.ki_user_scripts_dir, existing_files)

            cmd = content['cmd']
            if '${BOM_SCRIPT}' in cmd:
                cmd = cmd.replace ('${BOM_SCRIPT}', paths.ki_user_scripts_dir)

            add_bom_plugin_entry (paths, content['name'], cmd)

        else:
            print ("No BOM Plugin files found in %s" % target_path)


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

def write_yml_config (filepath, data):
    with open(filepath, 'w') as outfile:
        yaml.dump(data, outfile, default_flow_style=False)

def read_yml_config (filepath):
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


def output_table (headings, data):
    sizes = []

    for h in headings:
        sizes.append (len(h))

    for line in data:
        for j in range(0,min (len(headings), len(line))):
            sizes[j] = max (sizes[j], len(line[j]))
#
    for j in range(0, len(sizes)):
        sizes[j] = sizes[j] + 2

    s = ""
    for j in range(0,len(headings)):
        fmt = "%%-%ds" % sizes[j]
        s += fmt % headings[j]
    print (s)

    s = ""
    for j in range(0,len(headings)):
        s += '-' * sizes[j]
    print (s)


    for line in data:
        s = ""
        for j in range(0, min (len(headings), len(line))):
            fmt = "%%-%ds" % sizes[j]
            s += fmt % line[j]
        print (s)

        
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

        self.have_git = False
        self.git_message = False
        self.git_checked = False

    def remove_installed (self, publisher, package_name, content=None):

        files_to_remove = []

        if "installed" in self.config:
            installed = self.config['installed']
            new_list = []
            for p in installed:
                if p['publisher']==publisher and p['package']==package_name:

                    for c in p['content']:
                        if content is None or c['name'] == content['name']:
                            if 'files' in c:
                                #delete_files (p['files'])
                                files_to_remove.extend (c['files'])
                    #
                    if content:
                        p_new = copy.deepcopy(p)
                        p_new['content'] = [x for x in p_new['content'] if x['name'] != content['name']]
                        if p_new['content']:
                            new_list.append (p_new)
                else:
                    new_list.append (p)

            self.config['installed'] = new_list

        return files_to_remove

    # add or update
    def add_installed (self, publisher, package_name, 
                       apackage_file, apackage_url, 
                       package_to_install, content_to_install, files_to_install):
        installed = None
        if "installed" in self.config:
            installed = self.config['installed']

        new_package = {}
        if installed is None:
            installed = []
        else:
            existing = [p for p in installed if p['publisher']==publisher and p['package']==package_name]
            if existing:
                new_package = existing[0]

        #todo: content types ?

        new_package['publisher'] = publisher
        new_package['package'] = package_name
        new_package['version'] = package_to_install['version']
        new_package['package_file'] = apackage_file
        new_package['url'] = apackage_url

        # remove existing content if any
        if 'content' in new_package:
            contents = [x for x in new_package['content'] if x['name'] != content_to_install['name']]
        else:
            contents = []

        for content in package_to_install['content']:

            if content['name'] == content_to_install['name']:
                url = content['url']
                git_path = None
                if url.endswith(".git"):
                    if self.git_test():
                        git_path = os.path.join (self.paths.cache_dir, publisher, package_name, content['name'])
                        git_path = os.path.join (git_path, package_to_install['version'])

                installed_content = {}
                installed_content ['name'] = content['name'] 
                installed_content ['type'] = content['type'] 
                installed_content ['files'] = files_to_install
                if git_path:
                    installed_content ['git_repo'] = git_path
                contents.append (installed_content)

        new_package['content'] = contents

        #
        new_list = []
        for p in installed:
            if p['publisher']==publisher and p['package']==package_name:
                pass
            else:
                new_list.append (p)

        new_list.append (new_package)

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
                self.package_file = os.path.abspath (self.package_file)
                
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

    def install_package (self, apackage_file, target_version, actions, required_content = None):
    
        providers = read_package_info (apackage_file)
        if providers is None:
            return 1

        if not target_version:
            target_version = "latest"

        changes = True
        self.config ['default_package'] = apackage_file

        for provider in providers:
            print ("Installing package: %s, description: %s" % ( provider['name'], provider['description']))
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
            
            files = []     
            for content in package['content']:

                if required_content is None or required_content['name'] == content['name']:
                    target_path = os.path.join (self.paths.cache_dir, provider['publisher'], provider['name'], content['name'], actual_version)

                    if args.verbose:
                        print ("Data source: %s" % (content['url']))

                    if "download" in actions:
                        url = content['url']
                        if url.endswith(".git"):
                            if self.git_test():
                                git_path = os.path.join (self.paths.cache_dir, provider['publisher'], provider['name'], content['name'])
                                git_clone_or_update (url, git_path, actual_version, self.git_output)
                                git_path = os.path.join (git_path, actual_version)
                                ok = True
                            else:
                                print ("Skipping %s" % content['name'])
                                ok = False
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
                                files = install_content (self.paths, target_path, 
                                                           content['type'], content['filter'] if "filter" in content else "*/*",
                                                           provider['publisher'], provider['name'], actual_version,
                                                           content, required_content)

                                self.add_installed (provider['publisher'], provider['name'], 
                                                    apackage_file, 
                                                    self.package_url, 
                                                    package,  # package to install
                                                    content,  # content to install
                                                    files)
                                changes = True
                            else:
                                files = []
                                for extract in content['extract']:
                                    files.extend( install_content (self.paths, target_path,
                                                               extract['type'], extract['filter'] if "filter" in extract else "*/*",
                                                               provider['publisher'], provider['name'], actual_version,
                                                               content, required_content) )
                                # todo ?
                                self.add_installed (provider['publisher'], provider['name'], 
                                                    apackage_file, self.package_url, 
                                                    package, content,
                                                    files)
                                changes = True
            # for content
            #

        # for provider

        if changes and not args.test:
            write_yml_config (self.paths.kipi_config_filename, self.config)

        return 0

    def remove_package (self, publisher, package_name, content = None):
        temp = [p for p in self.config['installed'] if p['package'] == package_name]

        if publisher:
            packages = [p for p in temp if p['publisher'] == publisher]
        else:
            packages = temp

        err_code = 0
        files_to_remove = []

        changes = False
        if len(packages) == 1:
            # todo: get type?
            if content is None:
                # remove all
                print ("Removing package %s" % package_name)
                uninstall_content (self.paths, packages[0]['publisher'], package_name)
                files_to_remove = self.remove_installed (packages[0]['publisher'], package_name)
            else:
                print ("Removing package content %s" % content['name'])
                uninstall_content (self.paths, packages[0]['publisher'], package_name, content)
                files_to_remove = self.remove_installed (packages[0]['publisher'], package_name, content)

            changes = True
    
            if changes and not args.test:
                write_yml_config (self.paths.kipi_config_filename, self.config)
           
            return err_code, files_to_remove
        elif len(packages) > 1:
            print ("error: package name %s is ambiguous" % package_name)
            return 2, files_to_remove
        else:
            print ("error: package name %s not installed" % package_name)
            return 2, files_to_remove

    def list(self, check_for_updates=True, display_table=True):

        updates = []

        if "installed" in self.config and self.config['installed']:
            headings = ["Publisher", "Package name", "Content", "Installed Version (latest)"]
            if args.verbose:
                headings.append("Source")

            table = []

            for config_package in self.config['installed']:
                # get from url?
                # only if flag?
                if config_package['url']:
                    self.get_package_file (config_package['url'])

                #
                providers = read_package_info (config_package['package_file'])
                if providers:
                    for provider in providers:

                        installed_version = find_version (provider, config_package['version'])

                        first = True
                        #for content in installed_version['content']:
                        for content in config_package['content']:

                            latest_package = find_version (provider, "latest")

                            line = []
                            if first:
                                line.append (config_package['publisher'])
                                line.append (config_package['package'])
                                first = False
                            else:
                                line.append ("")
                                line.append ("")

                            line.append (content['name'])
            
                            ver = ""
                            update_available = False
                            if config_package['version'] == "latest":
                                if self.git_test():
                                    if "git_repo" in content:

                                        git_repo = os.path.join (self.paths.cache_dir, config_package['publisher'], config_package['package'], 
                                                                   content['name'],
                                                                   config_package['version'])
                                        ver = "git: %s" % get_git_status (git_repo)
                                        branch = get_git_branch_name (git_repo)
                                        status = get_git_branch_status (git_repo, branch)
                                        if status:
                                            ver += " (%s)" % status
                                            if status != "up to date":
                                                update_available = True

                                    else:
                                        vers = "git: unknown"
                                else:
                                    ver = "git: unknown"
                            else:
                                ver = config_package['version']
                                if latest_package and is_later_version (latest_package['version'], config_package ['version']):
                                    ver += " (%s)" % latest_package['version']
                                    update_available = True

                            if update_available:
                                if not config_package['package'] in updates:
                                    updates.append ([config_package, latest_package, content])

                            line.append (ver)

                            if config_package['url']:
                                line.append (config_package['url'])
                            elif "file" in config_package and config_package['file']:
                                line.append (config_package['file'])

                            table.append (line)

            #
            if display_table:
                output_table (headings, table)

        else:
            print ("no packages installed")

        return 0, updates

    # select from list of updatable_packages
    def get_matching (self, packages, publisher, package_name):
        result = []
        if publisher is None and package_name is None:
            result = packages
            return result

        for item in packages:
            config_package = item[0]
            select = True
            if publisher and config_package['publisher'] != publisher:
                select = False

            if select and package_name and 'name' in config_package and config_package['name'] != package_name:
                select = False

            if select and package_name and 'package' in config_package and config_package['package'] != package_name:
                select = False

            if select:
                result.append (item)

        return result


    def update_package (self, publisher, package_name):
        if "installed" in self.config and self.config['installed']:
            err_code, updatable_packages = self.list (check_for_updates=True, display_table=False)

            #
            temp = [p for p in self.config['installed'] if p['package'] == package_name]
            if publisher:
                packages = [p for p in temp if p['publisher'] == publisher]
            else:
                packages = temp

            update_packages = self.get_matching (updatable_packages, publisher, package_name)

            if len(update_packages) > 0:

                table = []
                headings = ["Publisher", "Package name", "Content", "Installed Version (latest)"]
                for config_package, latest_package, content in update_packages:
                    #print ("%-15s %-20s %s %s (%s)" % () )
                    line = [config_package['publisher'], config_package['package'], 
                            content['name'],
                            "%s (%s)" % (config_package['version'], latest_package['version'] ) ]
                    table.append (line)

                output_table (headings, table)

                ans = raw_input( "Update packages [Y] ? ")
                if ans == "" or ans.lower().startswith("y"):
                #
                    for config_package, latest_package, content in update_packages:
                        # remove current?
                        # remove_package (package)
                        self.package_url = config_package['url']

                        print ("Updating package %s, content %s" % (config_package['package'], content['name']) )

                        err_code, files_to_remove = self.remove_package (config_package['publisher'], config_package['package'], content)

                        self.install_package (config_package['package_file'], latest_package['version'], "download,install", content)
            else:
                print ("No updates available")
        else:
            print ("No packages installed")

        return 0

    def test(self):
        remove_bom_plugin_entry (self.paths, "fred")
        #add_bom_plugin_entry (self.paths, "fred", 'mycmd "arg1" "arg2"')

    def git_test(self):
        if not self.git_checked:
            self.have_git = git_check()
            self.git_checked = True

        if self.have_git:
            return True
        else:
            if not self.git_message:
                print ("error: git is required but is not installed")
                self.git_message = True
            return False

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
        kipi_config_folder = get_app_config_path("kipi")
        self.paths.kipi_config_filename = os.path.join (kipi_config_folder, "kipi.cfg")

        if os.path.exists(self.paths.kipi_config_filename):
            self.config = read_yml_config (self.paths.kipi_config_filename)
        else:
            self.config = None

        if args.config:
            if self.config is None:
                self.config = {}
                #self.config ['default_package'] = "kicad-official-libraries-v5.yml"
            self.config ['cache_path'] = args.config # todo check/default?
            make_folder (kipi_config_folder)
            write_yml_config (self.paths.kipi_config_filename, self.config)
            return 0

        if not self.config:
            print ("error: need configuration")
            print ("run kipi -c <cache_path>")
            return 1


        self.paths.cache_dir = self.config['cache_path']
        self.default_package_file = self.config ['default_package']

        self.paths.package_info_dir = os.path.join (self.paths.cache_dir, "_packages")

        self.paths.package_info_search_path = [".", self.paths.package_info_dir, "../packages"]

        user_documents = get_user_documents()
        self.paths.kicad_config_dir = get_app_config_path("kicad")

        #todo: get from config
        kicad_common = read_config_file (os.path.join (self.paths.kicad_config_dir, "kicad_common"))

        if 'KIGITHUB' in os.environ:
            self.paths.ki_github_url = os.environ['KIGITHUB']
        else:
            self.paths.ki_github_url = get_config_item (kicad_common, 'KIGITHUB')

        if 'KISYS3DMOD' in os.environ:
            self.paths.ki_packages3d_dir = os.environ['KISYS3DMOD']
        else:
            self.paths.ki_packages3d_dir = get_config_item (kicad_common, 'KISYS3DMOD')

        # also system templates?
        self.paths.ki_user_templates_dir = os.path.join(user_documents, "kicad", "template")

        if 'KICAD_PTEMPLATES' in os.environ:
            self.paths.ki_portable_templates_dir = os.environ['KICAD_PTEMPLATES']
        else:
            self.paths.ki_portable_templates_dir = get_config_item (kicad_common, 'KICAD_PTEMPLATES')

        self.paths.ki_user_scripts_dir = os.path.join(self.paths.kicad_config_dir, "scripting")

        #C:\Users\bob\AppData\Roaming\kicad\scripting
        #C:\Users\bob\AppData\Roaming\kicad\scripting\plugins

        # ~/.kicad_plugins/
        # C:\Users\bob\AppData\Roaming \kicad \scripts

        #
        #self.test()
        #return 1

        #
        self.git_message = False
        self.git_checked = False
        #self.have_git = git_check()
        

        if (args.install or args.update or args.remove) and get_running_processes("kicad") and not args.test:
            print ("error: cannot modify installed packages while kicad is running")
            return 2

        if args.update:
            err_code = self.update_package (None, args.package_spec)

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
            err_code, updates = self.list()

        elif args.download or args.install:
            err_code = self.get_package_file(args.package_spec)

            #todo: may need to remove first
            if err_code == 0:
                err_code = self.install_package(self.package_file, args.version, actions)

        elif args.remove:

            # remove any installed packages in pack_file
            # by publisher, name?
            err_code, files_to_remove = self.remove_package(None, args.package_spec)
            if files_to_remove:
                delete_files (files_to_remove)

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
