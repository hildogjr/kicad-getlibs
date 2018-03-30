#!/usr/bin/env python
from __future__ import print_function

import argparse
import glob
import json
import os
from subprocess import Popen
import subprocess
import sys
import shutil
import urllib
import urllib2
import yaml
import zipfile

from checksum import get_sha256_hash
from str_util import *
from lib_table import read_lib_table, write_lib_table

"""
KiCad-GetLibs
=============

A tool for downloading and installing kiCad packages, primarily for KiCad v5.

External dependencies: to clone git repos locally requires git, otherwise only zips can be used.

Runs on Windows, should run on Linux (MacOs might also work!).

Tested on Windows 7, 64 bit, not tested on other platforms.

"""

class Version:
    def __init__(self, s=None):
        self.major = 0
        self.minor = 0
        self.patch = 0
        self.pre_release = None
        if s:
            items = s.split(".")
            self.major = items[0]
            if len(items)>1:
                self.minor = items[1]
                if len(items)>2:
                    self.patch = items[2]
                    if "-" in self.patch:
                        self.pre_release = self.patch.split("-")[1]
                        self.patch = self.patch.split("-")[0]

    # return True of self > other
    def compare (self, other):
        if self.major > other.major:
            return True
        elif self.major == other.major:
            if self.minor > other.minor:
                return True
            elif self.minor == other.minor:
                if self.patch > other.patch:
                    return True
                elif self.patch == other.patch:
                    if (self.pre_release is None and not other.pre_release is None) or self.pre_release > other.pre_release:
                        return True
        return False

    def __str__ (self):
        return "%s %s %s %s" % (self.major, self.minor, self.patch, self.pre_release)
    __repr__= __str__


def is_later_version (a, b):
    ver_a = Version(a)
    return ver_a.compare (Version(b))

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

def write_list(filename, list):
    fw = open(filename, "w")
    for s in list:
        fw.write(s + "\n")
    fw.close()


def check_checksum(fname, checksum):

    actual_checksum = "SHA-256:" + get_sha256_hash(fname)

    if checksum != actual_checksum:
        print ("Error: bad hash, expected %s got %s" % (checksum, actual_checksum))
        return False

    return True

def make_folder (dir):
    if not os.path.exists(dir):
        try:
            os.makedirs(dir)
        except Exception, e:
            return False
    return True


def get_url(theurl, name):
    try:
        name, hdrs = urllib.urlretrieve(theurl, name)
    except IOError, e:
        print ("error: Can't retrieve %r to %r: %s" % (theurl, name, e))
        return False
    return True

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


# get footprints and symbols at specific version from release server
def get_tagged_version (version):
    fp_dir = os.path.join(cache_path, "kicad-footprints-" + version )
    lib_dir = os.path.join(cache_path, "kicad-library-" + version )
    
    if not os.path.exists (fp_dir):
        print ("Getting footprints for " + version)
        get_unzipped ("http://downloads.kicad-pcb.org/libraries/kicad-footprints-"+version+".zip", cache_path)
    else:
        print ("Already got " + fp_dir)

    fp_libs = [f for f in os.listdir(fp_dir) if os.path.isdir(os.path.join(fp_dir, f))]

    # symbols
    if not os.path.exists (lib_dir):
        print ("Getting symbols for " + version)
        get_unzipped ("http://downloads.kicad-pcb.org/libraries/kicad-library-"+version+".zip", cache_path)
    else:
        print ("Already got " + lib_dir)

    return fp_libs


# git latest symbols/footprints via github
def get_latest():

    if False:
        # get list of repos
        print ("Getting list of repos from github")
        full_list = []
        page = 1
        while True:
            req = urllib2.Request('https://api.github.com/users/kicad/repos?page=%d' % page)
            req.add_header('Accept', 'application/vnd.github.v3+json')
            req.add_header('User-Agent', 'hairymnstr-kicad-fetcher')
            res = urllib2.urlopen(req)
            repos = json.loads(res.read())
            for repo in repos:
                full_list.append(repo['clone_url'])
            if len(repos) < 30:
                break
            page += 1

        repos_to_get = []
        for repo in full_list:

            repo_name = repo.rsplit('/', 1)[1]
    
            if repo_name.split(".", 1)[1] == "pretty.git":
                print (repo, repo_name)
                repos_to_get.append(repo)
            elif  repo_name == "kicad-library.git":
                repos_to_get.append(repo)

    else:
        repos_to_get = []
        repos_to_get.append("https://github.com/KiCad/kicad-footprints.git")
        repos_to_get.append("https://github.com/KiCad/kicad-symbols.git")

    #  else:
    #    if not args.quiet:
    #      print ("ignore:", repo_name)

    ##
    write_list(os.path.join(cache_path, "list.txt"), repos_to_get)

    fp_path = os.path.join(cache_path, "kicad-footprints" )   # was footprints-latest
    #if not os.path.isdir(fp_path):
    #    os.makedirs(fp_path)

    for repo in repos_to_get:
        repo_name = repo.rsplit('/', 1)[1]
    
        name = repo_name.rstrip(".git")

        if repo_name.split(".", 1)[1] == "pretty.git":
            path = os.path.join(cache_path, "footprints-latest" )
            fp_libs.append (name)
        elif repo_name == "kicad-footprints.git":
            ##
            #path = os.path.join(cache_path, "footprints-latest-v5" )
            path = cache_path

        else:
            path = cache_path
            ##name = "library-latest"

        if os.path.isdir(os.path.join(path, name)):
            if not args.quiet:
                print ("Updating repo", repo_name)
            pr = Popen(["git", "pull"], cwd=os.path.join(path, name), stdout=git_output)
            pr.wait()
        else:
            cmd = ["git", "clone", repo, name]
            if not args.quiet:
                print ("Cloning repo", repo_name)
            if not args.verbose:
                # verbose mode
                cmd.append("-q")

            pr = Popen(cmd, cwd=path, stdout=git_output)
            pr.wait()

        #
        if repo_name == "kicad-footprints.git":
            #os.path.join(cache_path, "kicad-footprints" )

            for root, dirnames, filenames in os.walk(fp_path):
                for dirname in dirnames:
                    if dirname.endswith (".pretty"):
                        fp_libs.append (dirname)

        elif repo_name == "kicad-symbols.git":
            for filename in os.listdir(os.path.join(cache_path, "kicad-symbols")):
                if filename.endswith (".lib"):
                    sym_libs.append (filename)
        
    return fp_libs, sym_libs

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

def git_clone_or_update (repo_url, target_path, target_name):
  
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

def update_global_fp_table(publisher, package, version):
    update_global_table("fp", fp_libs, os.path.join(cache_path, fp_local), publisher, package, version)

def update_global_sym_table(publisher, package, version):
    update_global_table("sym", sym_libs, os.path.join(cache_path, "kicad-symbols"), publisher, package, version)

def update_global_table(table_type, update_libs, package_path, publisher, package, version):

    changes = False

    table_name = table_type + "-lib-table"

    if table_type=="fp":
        ext = ".pretty"
    else:
        ext = ".lib"

    # first purge old entries
    if os.path.exists(os.path.join(kicad_config, table_name)):
        libs = read_lib_table(os.path.join(kicad_config, table_name), table_type)

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
                if absolute:
                    lib['uri'] = os.path.abspath(os.path.join(package_path, lib['name'] + ext))
                else:
                    lib['uri'] = "${KISYSMOD}/" + lib['name'] + ext
                lib['options'] = u'publisher=%s|package=%s|version=%s' % (publisher, package, version)
                lib['descr'] = u'""'

                if args.verbose:
                    print ("Insert: ", lib_name)
                new_libs.append(lib)
                changes = true

    # finally, save the new lib-table
    if changes:
        # todo : create numbered backup
        backup_name = table_name + "-old"
        if args.test:
            print ("Would create backup of %s to %s" % (table_name, os.path.join(kicad_config, backup_name) ))
        else:
            if args.verbose:
                print ("Creating backup of %s to %s" % (table_name, os.path.join(kicad_config, backup_name) ))
            shutil.copy2(os.path.join(kicad_config, table_name), os.path.join(kicad_config, backup_name))

        if args.test:
            print ("Would save %s to %s" % (table_name, os.path.join(kicad_config, table_name) ))
        else:
            if args.verbose:
                print ("Saving %s to %s" % (table_name, os.path.join(kicad_config, table_name) ))
            write_lib_table(os.path.join(kicad_config, table_name), table_type, new_libs)


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
            file = os.path.join(destination_path, item.split(os.sep)[-1])
            if not os.path.exists(file) or overwrite:

                if args.test:
                    print ("Would copy %s to %s" % (item, file))
                else:
                    shutil.copyfile(item, file)
                    copied_files.append (file)

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
            
        dir = os.path.dirname (dest_file)
        if not os.path.exists (dir):
            if args.test:
                print ("Would create %s " % dir)
            else:
                os.makedirs(dir)
                copied_files.append (dir)

        if args.test:
            # print ("Would copy %s to %s" % (filename, dest_file))
            pass
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

    for file in files:
        if os.path.isdir (file):
            pass
        else:
            if args.test:
                print ("would delete file %s" % (file))
            else:
                if args.verbose:
                    print ("deleting %s" % (file))

                try:
                    os.remove (file)
                except Exception, e:
                    print ("error: can't delete file %s: %s" % (file, e.strerror))

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
                    except Exception, e:
                        print ("error: can't delete directory %s: %s" % (item, e.strerror))
                else:
                    if args.verbose:
                        print ("%s is not empty" % (item))



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
        except Exception as e:
            print (e)
            return False


def get_libs (target_path, file_spec, filter, find_dirs):
    libs = []
    if filter == "*/*":
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
        if isinstance (filter, basestring):
            filter = [filter]
        for f in filter:
            f = f.strip()
            path = target_path + os.sep + f
            if (os.path.isdir(path)):
                path = os.path.join (path, "*.*")
            for filename in glob.glob(path):
                if filename.endswith (file_spec):
                    libs.append (filename)
    return libs

def uninstall_libraries (target_path, type, filter, publisher, package_name, target_version):

    if "footprint" in type:
        update_global_table("fp", None, target_path, publisher, package_name, target_version)

    if "symbol" in type:
        update_global_table("sym", None, target_path, publisher, package_name, target_version)

def install_libraries (target_path, type, filter, publisher, package_name, target_version):

    files = []

    if "footprint" in type:
        # kicad_mod, other supported types
        libs = get_libs (target_path, ".pretty", filter, True)

        if len(libs) > 0:
            print ("footprint libs: ", len(libs))

            update_global_table("fp", libs, target_path, publisher, package_name, target_version)
        else:
            print ("No footprint libraries found in %s" % target_path)

    if "symbol" in type:
        libs = get_libs (target_path, ".lib", filter, False)
        # future: .sweet

        if len(libs) > 0:
            print ("Symbol libs: ", len(libs))
            update_global_table("sym", libs, target_path, publisher, package_name, target_version)
        else:
            print ("No symbol libraries found in %s" % target_path)

    if "3dmodel" in type:
        libs = get_libs (target_path, ".wrl", filter, False)
        libs.extend (get_libs (target_path, ".step", filter, False))
       
        # copy to ...

        if len(libs) > 0:
            print ("3D model files: ", len(libs))
            # 
            # make_folder (ki_packages3d_path)
            ok = False
            if os.path.exists (ki_packages3d_path):
                if is_writable (ki_packages3d_path):
                    ok = True
                else:
                    print ("error: can't write to %s" % ki_packages3d_path)
            else:
                if make_folder (ki_packages3d_path):
                    ok = True
                else:
                    print ("error: can't create %s" % ki_packages3d_path)

            if ok:
                files = copy_files(libs, target_path, ki_packages3d_path)
        else:
            print ("No 3D Models found in %s" % target_path)

    if "template" in type:
        # todo
        # could also check for 'meta' folder
        # also worksheet files?
        # copy to portable templates?
        libs = get_libs (target_path, ".pro", filter, False)
        template_folders = []
        for lib in libs:
            path = get_path (lib)
            if args.verbose:
                print ("template %s" % path)
            template_folders.append (path)

        # copy to user templates

        if len(template_folders) > 0:
            print ("Templates: ", len(template_folders))
            make_folder (ki_user_templates)
            files = copy_folders (template_folders, target_path, ki_user_templates)
        else:
            print ("No templates found in %s" % target_path)

    if "script" in type:
        # check for simple vs complex scripts?

        scripts = get_libs (target_path, ".py", filter, False)

        if len(scripts) > 0:
            print ("Scripts : ", len(scripts))

            if isinstance (filter, basestring):
                path = get_path (target_path + os.sep + filter)
            else:
                path = target_path

            make_folder (ki_user_scripts)
            files = copy_files (scripts, path, ki_user_scripts)
        else:
            print ("No scripts found in %s" % target_path)

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

                #print (kwargs)

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

                # self._execute_script(**kwargs)  # now we can execute the script

            return providers
        except yaml.YAMLError as exc:
            print(exc)
            return None

def write_config (filepath, data):
    with open(filepath, 'w') as outfile:
        yaml.dump(data, outfile, default_flow_style=False)

def read_config (filepath):
    if os.path.exists (filepath):
        with open(filepath, 'r') as stream:
            try:
                parsed = yaml.load(stream)  # parse file

                if parsed is None:
                    print("error: empty config file!")
                    return parsed

                return parsed

            except yaml.YAMLError as exc:
                print (exc)
                return None
            except:
                print("Unexpected error:", sys.exc_info()[0])
                return None
    else:
        return None

def remove_installed (publisher, package_name, target_version):

    if "installed" in config:
        installed = config['installed']
        new_list = []
        for p in installed:
            if p['publisher']==publisher and p['package']==package_name:
                #pass
                delete_files (p['files'])
            else:
                new_list.append (p)

        #new_list.append (package)
        config['installed'] = new_list


def add_installed (publisher, package_name, target_version, package_file, package_url, files, git_path):
    installed = None
    if "installed" in config:
        installed = config['installed']

    if installed == None:
        installed = []

    package = {}
    package['publisher'] = publisher
    package['package'] = package_name
    package['version'] = target_version
    package['package_file'] = package_file
    package['url'] = package_url
    package['files'] = files
    package['git_repo'] = git_path

    new_list = []
    for p in installed:
        if p['publisher']==publisher and p['package']==package_name:
            pass
        else:
            new_list.append (p)

    new_list.append (package)
    config['installed'] = new_list

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

def get_package_file(_package_file):
    global package_file
    global package_url

    if _package_file:
        if _package_file.startswith("http"):
            package_url = _package_file
            package_file = os.path.join (package_info_dir, get_url_name (_package_file))
            package_file = change_extension (package_file, ".yml")
            make_folder (package_info_dir)
            get_url (_package_file, package_file)
        else:
            package_url = None
            if not _package_file.endswith (".yml"):
                _package_file = change_extension (_package_file, ".yml")
            package_file = find_file ( package_info_search_path, _package_file)
                
        if os.path.exists (package_file):
            providers = read_package_info (package_file)
        else:
            print ("error: can't open package file %s" % package_file)
            return 1

    elif os.path.exists (default_package):
        package_file = default_package 
        providers = read_package_info (default_package)
    else:
        print ("error: No package file specified")
        return 1

    if providers == None:
        print ("error: No package info found")
        return 1

    return 0

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

def perform_actions(package_file, version, actions):
    
    providers = read_package_info (package_file)
    if providers == None:
        return 1

    if version:
        target_version = version
    else:
        target_version = "latest"

    changes = True
    config ['default_package'] = package_file

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
        package = match_package
        #for package in provider['packages']:
        #if package['version'] == target_version:
        # print ("   package: ver: %s" % ( package['version']))
                 
        for content in package['content']:
            #print "      content: type: %s url: %s filters: %s" % ( 
            #    content['type'], content['url'],
            #    content['filter'] if "filter" in content else "*/*"
            #    )

            target_path = os.path.join (cache_path, provider['publisher'], provider['name'], content['name'], target_version)

            print ("Data source: %s" % (content['url']))

            if "download" in actions:
                url = content['url']
                if url.endswith(".git"):
                    git_path = os.path.join (cache_path, provider['publisher'], provider['name'], content['name'])
                    git_clone_or_update (url, git_path, target_version)

                    git_path = os.path.join (git_path, target_version)
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
                        files = install_libraries (target_path, content['type'],
                                            content['filter'] if "filter" in content else "*/*",
                                            provider['publisher'], provider['name'], target_version)

                        add_installed (provider['publisher'], provider['name'], package['version'], package_file, package_url, files, git_path)
                        changes = True

                    else:
                        for extract in content['extract']:
                            files = install_libraries (target_path,
                                                extract['type'],
                                                extract['filter'] if "filter" in extract else "*/*",
                                                provider['publisher'], provider['name'], target_version)

                            add_installed (provider['publisher'], provider['name'], package['version'], package_file, package_url, files, git_path)
                            changes = True

            elif "remove" in actions:
                if "type" in content:
                    uninstall_libraries (target_path, content['type'],
                                            content['filter'] if "filter" in content else "*/*",
                                            provider['publisher'], provider['name'], target_version)

                    remove_installed (provider['publisher'], provider['name'], target_version)
                    changes = True

                else:
                    for extract in content['extract']:
                        uninstall_libraries (target_path,
                                            extract['type'],
                                            extract['filter'] if "filter" in extract else "*/*",
                                            provider['publisher'], provider['name'], target_version)

                        remove_installed (provider['publisher'], provider['name'], target_version)
                        changes = True

        print ("")
    # for

    if changes and not args.test:
        write_config (getlibs_config_file, config)

    return 0
#
# main
#
parser = argparse.ArgumentParser(description="Download and install KiCad data packages")

parser.add_argument("package_file",     help="specifies the package to download/install", nargs='?')
parser.add_argument("version",          help='a valid version from the package file or "latest"', nargs='?')

parser.add_argument("-v", "--verbose",  help="enable verbose output", action="store_true")
parser.add_argument("-q", "--quiet",    help="suppress messages", action="store_true")
parser.add_argument("-t", "--test",     help="dry run", action="store_true")

parser.add_argument("-c", "--config",  metavar="local_folder", help="configure get-libs. <local_folder> is the folder which stores downloaded package data")

parser.add_argument("-d", "--download", help="download the specified package data", action="store_true")
parser.add_argument("-i", "--install",  help="install package data into KiCad (implies download)", action="store_true")
parser.add_argument("-r", "--remove" ,  help="remove an installed package from KiCad", action="store_true")
parser.add_argument("-u", "--update" ,  help="update packages installed in KiCad", action="store_true")
parser.add_argument("-l", "--list",     help="list installed packages", action="store_true")

parser.add_argument("--catalog",        help="list local package files", action="store_true")

args = parser.parse_args()

# default is to dump git output to null, i.e. not verbose
git_output = open(os.devnull, "w")
absolute = True
actions = ""

if args.verbose:
    git_output.close()
    git_output = None

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

#if len(args) < 1:
#    try:
#        kisysmod = os.environ['KISYSMOD']
#    except KeyError:
#        print ("error: No local folder specified, and couldn't read KISYSMOD environment variable")
#        usage()
#        sys.exit(-2)
#else:
#    kisysmod = args[0]

getlibs_config_folder = get_config_path("kicad-getlibs")
getlibs_config_file = os.path.join (getlibs_config_folder, "kicad-getlibs.cfg")

if os.path.exists(getlibs_config_file):
    config = read_config (getlibs_config_file)
else:
    config = None

if args.config:
    if config == None:
        config = {}
        config ['default_package'] = "kicad-official-libraries-v5.yml"
    config ['cache_path'] = args.config # todo check/default?
    make_folder (getlibs_config_folder)
    write_config (getlibs_config_file, config)
    sys.exit(0)

if not config:
    print ("error: need configuration")
    print ("run kicad-getlibs.py -c <cache_path>")
    sys.exit(1)


cache_path = config['cache_path']
default_package = config ['default_package']

package_info_dir = os.path.join (cache_path, "packages")

package_info_search_path = [".", package_info_dir, "packages"]

user_documents = get_user_documents()
kicad_config = get_config_path("kicad")

ki_packages3d_path = os.environ['KISYS3DMOD']
# also system templates?
ki_user_templates = os.path.join(user_documents, "kicad", "template")
ki_portable_templates_path = os.environ['KICAD_PTEMPLATES']

ki_user_scripts = os.path.join(kicad_config, "scripting")

#C:\Users\bob\AppData\Roaming\kicad\scripting
#C:\Users\bob\AppData\Roaming\kicad\scripting\plugins

# ~/.kicad_plugins/
# C:\Users\bob\AppData\Roaming \kicad \scripts

#
have_git = git_check()

if args.update:
    if "installed" in config and config['installed']:
        update_packages = []
        for package in config['installed']:
            # get from url?
            # only if flag?
            if package['url']:
                get_package_file (package['url'])

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

                    package_url = package['url']
                    perform_actions (package['package_file'], package['version'], "remove")

                    perform_actions (package['package_file'], latest_package['version'], "download,install")

        else:
            print ("No updates available")
    else:
        print ("no packages installed")
    err_code = 0

elif args.catalog:
    # 
    files = find_files (package_info_search_path, "*.yml")

    print ("Local package info files:")
    print ("")

    if files:
        for f in files:
            print ("  " + f)
    else:
        print ("No local package info files found")
    err_code = 0

elif args.list:
    if "installed" in config and config['installed']:
        print ("%-15s %-35s %s" % ("Publisher", "Package name", "Installed Version (latest)") )
        print ("")                                                    
        for package in config['installed']:
            # get from url?
            # only if flag?
            if package['url']:
                get_package_file (package['url'])

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
                s += " %s" % package['version']
                if latest_package and is_later_version (latest_package['version'], package ['version']):
                    s += " (latest %s)" % latest_package['version']

            if package['url']:
                s += "%s" % package['url']

            print (s)

            if args.verbose:
                if package['files']:
                    for f in package['files']:
                        print ("   %s" % (f))

    else:
        print ("no packages installed")
    err_code = 0

elif actions:
    err_code = get_package_file(args.package_file)

    if err_code == 0:
        err_code = perform_actions(package_file, args.version, actions)
else:
    parser.print_help()
    err_code = 0

sys.exit(err_code)

