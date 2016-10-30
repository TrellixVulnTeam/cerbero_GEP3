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
import hashlib

from cerbero.commands import Command, register_command, build
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m
from cerbero.errors import PackageNotFoundError, UsageError
from cerbero.packages.packager import Packager
from cerbero.packages.packagesstore import PackagesStore
from cerbero.packages.disttarball import DistTarball
from cerbero.utils import shell

class Package(Command):
    doc = N_('Creates a distribution package')
    name = 'package'

    def __init__(self):
        Command.__init__(self,
            [ArgparseArgument('package', nargs=1,
                             help=_('name of the package to create')),
            ArgparseArgument('-o', '--output-dir', default='.',
                             help=_('Output directory for the tarball file')),
            ArgparseArgument('-t', '--tarball', action='store_true',
                default=False,
                help=_('Creates a tarball instead of a native package')),
            ArgparseArgument('-f', '--force', action='store_true',
                default=False, help=_('Delete any existing package file')),
            ArgparseArgument('-d', '--no-devel', action='store_false',
                default=False, help=_('Do not create the development version '
                    'of this package')),
            ArgparseArgument('-s', '--skip-deps-build', action='store_true',
                default=False, help=_('Do not build the recipes needed to '
                    'create this package (conflicts with --only-build-deps)')),
            ArgparseArgument('-b', '--only-build-deps', action='store_true',
                default=False, help=_('Only build the recipes needed to '
                    'create this package (conflicts with --skip-deps-build)')),
            ArgparseArgument('-k', '--keep-temp', action='store_true',
                default=False, help=_('Keep temporary files for debug')),
            ])

    def run(self, config, args):
        self.store = PackagesStore(config)
        p = self.store.get_package(args.package[0])

        if args.skip_deps_build and args.only_build_deps:
            raise UsageError(_("Cannot use --skip-deps-build together with "
                    "--only-build-deps"))

        if not args.skip_deps_build:
            self._build_deps(config, p)

        if args.only_build_deps:
            return

        if p is None:
            raise PackageNotFoundError(args.package[0])
        if args.tarball:
            pkg = DistTarball(config, p, self.store)
        else:
            pkg = Packager(config, p, self.store)
        m.action(_("Creating package for %s") % p.name)
        p.pre_package()
        paths = pkg.pack(os.path.abspath(args.output_dir), not args.no_devel,
                         args.force, args.keep_temp)
        if None in paths:
            paths.remove(None)

        paths = p.post_package(paths) or paths
        for p in paths:
            BUF_SIZE = 65536  # 64kb chunks
            sha1 = hashlib.sha1()
            with open(os.path.abspath(p), 'rb') as f:
                while True:
                    data = f.read(BUF_SIZE)
                    if not data:
                        break
                    sha1.update(data)
            sha1sum = sha1.hexdigest()

            m.action(_("Package successfully created in %s %s") % (os.path.abspath(p), sha1sum))
            # Generate the sha1sum file
            with open('%s.sha1' % p, 'w+') as sha1file:
                sha1file.write(sha1sum)

    def _build_deps(self, config, package):
        build_command = build.Build()
        build_command.runargs(config, package.recipes_dependencies(),
            cookbook=self.store.cookbook)


register_command(Package)
