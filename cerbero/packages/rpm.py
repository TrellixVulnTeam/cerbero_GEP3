# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Andoni Morales Alastruey <ylatuya@gmail.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import os
import shutil
import tempfile
import tarfile

from cerbero.config import Architecture
from cerbero.enums import Distro, DistroVersion
from cerbero.errors import FatalError, EmptyPackageError
from cerbero.packages import PackageType
from cerbero.packages.linux import LinuxPackager
from cerbero.packages.package import MetaPackage
from cerbero.utils import shell, _
from functools import reduce


SPEC_TPL = '''
%%define _topdir %(topdir)s
%%define _package_name %(package_name)s
%%undefine _debugsource_packages
%%undefine _debuginfo_subpackages

Name:           %(p_prefix)s%(name)s
Version:        %(version)s
Release:        1
Summary:        %(summary)s
Source:         %(source)s
Group:          Applications/Internet
License:        %(licenses)s
Prefix:         %(prefix)s
Packager:       %(packager)s
Vendor:         %(vendor)s
%(url)s
%(requires)s
%(provides_conflicts_obsoletes)s

%%description
%(description)s

%(devel_package)s

%%prep
%%setup -n %%{_package_name}

%%build

%%install
mkdir -p $RPM_BUILD_ROOT/%%{prefix}
cp -r $RPM_BUILD_DIR/%%{_package_name}/* $RPM_BUILD_ROOT/%%{prefix}

# Workaround to remove full source dir paths from debuginfo packages
# (tested in Fedora 16/17).
#
# What happens is that rpmbuild invokes find-debuginfo.sh which in turn
# calls debugedit passing $RPM_BUILD_DIR as the "base-dir" param (-b) value.
# debugedit then removes the "base-dir" path from debug information.
#
# Normally packages are built inside $RPM_BUILD_DIR, thus resulting in proper
# debuginfo packages, but as we are building our recipes at $sources_dir and
# only including binaries here directly, no path would be removed and debuginfo
# packages containing full paths to source files would be used.
#
# Setting RPM_BUILD_DIR to $sources_dir should do the trick, setting here and
# hoping for the best.
export RPM_BUILD_DIR=%(sources_dir)s

%%clean
rm -rf $RPM_BUILD_ROOT

%(scripts)s

%%files
%(files)s

%(devel_files)s
'''


DEVEL_PACKAGE_TPL = '''
%%package devel
%(requires)s
Summary: %(summary)s
%(provides_conflicts_obsoletes)s

%%description devel
%(description)s
'''

META_SPEC_TPL = '''
%%define _topdir %(topdir)s
%%define _package_name %(package_name)s

Name:           %(p_prefix)s%(name)s
Version:        %(version)s
Release:        1
Summary:        %(summary)s
Group:          Applications/Internet
License:        %(licenses)s
Packager:       %(packager)s
Vendor:         %(vendor)s
%(url)s

%(requires)s

%%description
%(description)s

%(devel_package)s

%%prep

%%build

%%install

%%clean
rm -rf $RPM_BUILD_ROOT

%%files

%(devel_files)s
'''

REQUIRE_TPL = 'Requires: %s\n'
DEVEL_TPL = '%%files devel \n%s'
URL_TPL = 'URL: %s\n'
PRE_TPL = '%%pre\n'
POST_TPL = '%%post\n'
POSTUN_TPL = '%%postun\n'


class RPMPackager(LinuxPackager):

    def __init__(self, config, package, store):
        LinuxPackager.__init__(self, config, package, store)

    def create_tree(self, tmpdir):
        # create a tmp dir to use as topdir
        if tmpdir is None:
            tmpdir = tempfile.mkdtemp(dir=self.config.home_dir)
            for d in ['BUILD', 'SOURCES', 'RPMS', 'SRPMS', 'SPECS']:
                os.mkdir(os.path.join(tmpdir, d))
        return (tmpdir, os.path.join(tmpdir, 'RPMS'),
                os.path.join(tmpdir, 'SOURCES'))

    def setup_source(self, tarball, tmpdir, packagedir, srcdir):
        with tarfile.open(tarball, 'r:bz2') as tar:
            def is_within_directory(directory, target):
                
                abs_directory = os.path.abspath(directory)
                abs_target = os.path.abspath(target)
            
                prefix = os.path.commonprefix([abs_directory, abs_target])
                
                return prefix == abs_directory
            
            def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
            
                for member in tar.getmembers():
                    member_path = os.path.join(path, member.name)
                    if not is_within_directory(path, member_path):
                        raise Exception("Attempted Path Traversal in Tar File")
            
                tar.extractall(path, members, numeric_owner=numeric_owner) 
                
            
            safe_extract(tar, srcdir)
        os.remove(tarball)

        root_path = os.path.join(srcdir, self.full_package_name)
        self.package.pre_build(root_path)

        tarname = os.path.split(tarball)[1]
        if tarname.endswith('.bz2'):
            tarname = tarname[:-4]

        with tarfile.open(os.path.join(srcdir, tarname), 'w') as tar:
            tar.add(root_path, self.full_package_name)

        shutil.rmtree(root_path)
        return tarname

    def prepare(self, tarname, tmpdir, packagedir, srcdir):
        try:
            runtime_files = self._files_string_list(PackageType.RUNTIME)
        except EmptyPackageError:
            runtime_files = ''

        if self.install_dir not in ['/usr', '/usr/local']:
            runtime_files = runtime_files + '\n'+os.path.join(self.install_dir, '')

        if runtime_files or self.package.build_meta_package:
            self.package.has_runtime_package = True
        else:
            self.package.has_runtime_package = False

        if self.devel:
            devel_package, devel_files = self._devel_package_and_files()
        else:
            devel_package, devel_files = ('', '')

        if self.package.build_meta_package:
            template = META_SPEC_TPL
            requires = \
                self._get_meta_requires(PackageType.RUNTIME)
            self.package.has_devel_package = True
        else:
            self.package.has_devel_package = bool(devel_files)
            template = SPEC_TPL
            requires = self._get_requires(PackageType.RUNTIME)

        licenses = [self.package.license]
        if not self.package.build_meta_package:
            licenses.extend(self.recipes_licenses())
            licenses = sorted(list(set(licenses)))

        template_dict = {
            'name': self.package.name,
            'p_prefix': self.package_prefix,
            'version': self.package.version,
            'package_name': self.full_package_name,
            'summary': self.package.shortdesc,
            'description': self.package.longdesc != 'default' and
            self.package.longdesc or self.package.shortdesc,
            'licenses': ' and '.join([l.acronym for l in licenses]),
            'packager': self.packager,
            'vendor': self.package.vendor,
            'url': URL_TPL % self.package.url if
            self.package.url != 'default' else '',
            'requires': requires,
            'prefix': self.install_dir,
            'source': tarname,
            'topdir': tmpdir,
            'devel_package': devel_package,
            'devel_files': devel_files,
            'files': runtime_files,
            'sources_dir': self.config.sources}

        template_dict['provides_conflicts_obsoletes'] = ''
        provides = self.package.provides[Distro.REDHAT][PackageType.RUNTIME]
        conflicts = self.package.conflicts[Distro.REDHAT][PackageType.RUNTIME]
        obsoletes = self.package.replaces_obsoletes[Distro.REDHAT][PackageType.RUNTIME]
        if provides:
            template_dict['provides_conflicts_obsoletes'] += 'Provides: %s' % ', '.join(provides)
        if conflicts:
            template_dict['provides_conflicts_obsoletes'] += '\nConflicts: %s' % ', '.join(conflicts)
        if obsoletes:
            template_dict['provides_conflicts_obsoletes'] += '\nObsoletes: %s' % ', '.join(obsoletes)

        scripts = ''

        if os.path.exists(self.package.resources_preinstall):
            scripts += "{}{}\n".format(
                PRE_TPL,
                open(self.package.resources_preinstall).read())
        if os.path.exists(self.package.resources_postinstall):
            scripts += "{}{}\n".format(
                POST_TPL,
                open(self.package.resources_postinstall).read())
        if os.path.exists(self.package.resources_postremove):
            scripts += "{}{}\n".format(
                POSTUN_TPL,
                open(self.package.resources_postremove).read())
        # Allow usage of templates in post scripts
        scripts = scripts % template_dict
        template_dict.update({'scripts': scripts})

        self._spec_str = template % template_dict

        self.spec_path = os.path.join(tmpdir, '%s.spec' % self.package.name)
        with open(self.spec_path, 'w') as f:
            f.write(self._spec_str)

    def build(self, output_dir, tarname, tmpdir, packagedir, srcdir):
        if self.config.target_arch == Architecture.X86:
            target = 'i686-redhat-linux'
        elif self.config.target_arch == Architecture.X86_64:
            target = 'x86_64-redhat-linux'
        else:
            raise FatalError(_('Architecture %s not supported') %
                             self.config.target_arch)

        extra_options = ''
        if self._rpmbuild_support_nodebuginfo():
            extra_options = '--nodebuginfo'

        shell.call('rpmbuild -bb %s --buildroot %s/buildroot --target %s %s' % (
            extra_options, tmpdir, target, self.spec_path))

        paths = []
        for d in os.listdir(packagedir):
            for f in os.listdir(os.path.join(packagedir, d)):
                out_path = os.path.join(output_dir, f)
                if os.path.exists(out_path):
                    os.remove(out_path)
                paths.append(out_path)
                shutil.move(os.path.join(packagedir, d, f), output_dir)
        return paths

    def _rpmbuild_support_nodebuginfo(self):
        if not self.config.distro == Distro.REDHAT:
            return False

        if ("fedora" in self.config.distro_version
                and self.config.distro_version > DistroVersion.FEDORA_26):
            return True

        if ("redhat" in self.config.distro_version
                and self.config.distro_version > DistroVersion.REDHAT_7):
            return True

        return False

    def _get_meta_requires(self, package_type):
        devel_suffix = ''
        if package_type == PackageType.DEVEL:
            devel_suffix = '-devel'
        requires, recommends, suggests = \
            self.get_meta_requires(package_type, devel_suffix)
        requires = ''.join([REQUIRE_TPL % x for x in requires + recommends])
        return requires

    def _get_requires(self, package_type):
        devel_suffix = ''
        if package_type == PackageType.DEVEL:
            devel_suffix = '-devel'
        deps = self.get_requires(package_type, devel_suffix)
        return reduce(lambda x, y: x + REQUIRE_TPL % y, deps, '')

    def _files_string_list(self, package_type):
        if self.package.build_meta_package:
            return ''
        files = self.files_list(package_type)
        for f in [x for x in files if x.endswith('.py')]:
            if f + 'c' not in files:
                files.append(f + 'c')
            if f + 'o' not in files:
                files.append(f + 'o')
        return '\n'.join([os.path.join('%{prefix}',  x) for x in files])

    def _devel_package_and_files(self):
        args = {}
        args['summary'] = 'Development files for %s' % self.package.name
        args['description'] = args['summary']
        if self.package.build_meta_package:
            args['requires'] = self._get_meta_requires(PackageType.DEVEL)
        else:
            args['requires'] = self._get_requires(PackageType.DEVEL)
        args['name'] = self.package.name
        args['p_prefix'] = self.package_prefix

        provides = ['%(p_prefix)s%(name)s-devel' % args] + self.package.provides[Distro.REDHAT][PackageType.DEVEL]
        conflicts = self.package.conflicts[Distro.REDHAT][PackageType.DEVEL]
        obsoletes = self.package.replaces_obsoletes[Distro.REDHAT][PackageType.DEVEL]
        args['provides_conflicts_obsoletes'] = 'Provides: %s' % ', '.join(provides)
        if conflicts:
            args['provides_conflicts_obsoletes'] += '\nConflicts: %s' % ', '.join(conflicts)
        if obsoletes:
            args['provides_conflicts_obsoletes'] += '\nObsoletes: %s' % ', '.join(obsoletes)

        try:
            devel = DEVEL_TPL % self._files_string_list(PackageType.DEVEL)
        except EmptyPackageError:
            devel = ''
        return DEVEL_PACKAGE_TPL % args, devel


class Packager(object):

    def __new__(klass, config, package, store):
        return RPMPackager(config, package, store)


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro
    register_packager(Distro.REDHAT, Packager)
    register_packager(Distro.SUSE, Packager)
