@echo off

del dist\*

echo Building cart
python setup.py sdist

echo Putting wheel on
python setup.py bdist_wheel

if /%1/ == /upload/ (
  echo Uploading

  twine upload dist/*
  C:\Python_progs\bump_version\bump_version\bump_version.py kipi\__init__.py
)
 