KiPI
====

A tool for downloading and installing kiCad packages, primarily for KiCad v5.

Runs on Windows, should run on Linux (MacOs might also work).

Description
-----------

Currently supports footprints, symbols and templates. Configurations for KiCad
official v5 libraries and templates, SparkFun, DigiKey and Walter Lain libraries.

Typically where available, point releases are downloaded as a zip file. Otherwise, latest
versions of git repositories can be cloned locally.

This script can use git to:

1. Clone a repository if you don't have it
2. Pull the latest repository if you already have it locally (does an update).

Content types:

- Footprints can be installed to fp-lib-table.
- Symbols can be installed to sym-lib-table.
- Templates are copied to ~/Documents/kicad/templates
- 3dmodels are copied to ${KISYS3DMOD}
- Scripts are copied to ${APPDATA}/kicad/scripting

Existing xx-lib-table will be saved to xx-lib-table-old.

Usage
-----

`kipi [options] <package spec> [<version>]`

Package spec contains the packages to download/install.
Version is a valid version from the package file or "latest".

Options are:

-h, --help  shows a help screen on the command line

-v, --verbose  show verbose messages

-q, --quiet  don't show logging

-t, --test  dry run, don't perform actions

--config <local folder>  configure kipi. The local folder is the folder you want all your local data put in.

--download  download package data only

--install  install package data into KiCad (implies download)

--list  list installed packages

--remove  remove an installed package from KiCad

--update  update installed packages


**Example Usage**

`kipi --config c:\\kicad_data`

`kipi -v --install https://raw.githubusercontent.com/bobc/kicad-getlibs/master/packages/kicad-official-libraries-v5-no-3d.yml`

**Dependencies**

- You need to have git installed to clone/update local git repositories.

Otherwise it should just run with a standard distribution of python 2.x, there
are no special libraries used.

Bugs/Feature Requests
----------------------

Please raise issue on github.

Credits
-------

KiPI is derived from project https://github.com/hairymnstr/kicad-getlibs.


Content Types
=============

====================  ==========  ==========
Content type          Kicad v4    KiCad v5
====================  ==========  ==========
footprint             Yes         Yes
symbol                No          Yes
3dmodel               Yes*        Yes*
template              Yes         Yes
script                No          Yes
====================  ==========  ==========

Footprint
----------
Footprints are installed in global fp-lib-table.

Symbol
-------
- [v5] Symbols are installed in global sym-lib-table.
- [v4] Installing symbols is not supported because sym-lib-table is not supported in v4

3dmodel
--------
3dmodels can be installed if KISYS3DMOD is a writable location by user and does
not require admin permissions. On Windows the default path c:\\program files\\...
is not writable, so the user must re-configure KISYS3DMOD to writable location,
e.g "C:\\kicad_data\\3dmodels"

Template
---------
Templates are installed to user's templates folder.

Script
-------
Scripts may be pcbnew scripts or footprints wizards.

- [v5] Scripts are copied to global kicad/scripting folder.
- [v4] May work on Linux but does not work on Windows since v4 does not have a search path for user scripts.


