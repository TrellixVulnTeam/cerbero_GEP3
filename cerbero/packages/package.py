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

from cerbero.build.filesprovider import FilesProvider
from cerbero.enums import License, Platform
from cerbero.packages import PackageType
from cerbero.utils import remove_list_duplicates
from cerbero.errors import FatalError


class PackageBase(object):
    '''
    Base class for packages with the common field to describe a package

    @cvar name: name of the package
    @type name: str
    @cvar shortdesc: Short description of the package
    @type shortdesc: str
    @cvar longdesc: Long description of the package
    @type longdesc: str
    @cvar version: version of the package
    @type version: str
    @cvar codename: codename of the release
    @type codename: str
    @cvar uuid: unique id for this package
    @type uuid: str
    @cvar license: package license
    @type license: License
    @cvar vendor: vendor for this package
    @type vendor: str
    @cvar org: organization for this package (eg: net.foo.bar)
    @type org: str
    @cvar url: url for this pacakge
    @type url: str
    @cvar sys_deps: system dependencies for this package
    @type sys_deps: dict
    @cvar sys_deps_devel: development system dependencies for this package
    @type sys_deps_devel: dict
    @cvar ignore_package_prefix: don't use the package prefix set in the config
    @type ignore_package_prefix: bool
    @cvar relocate_osx_binaries: relocate osx binaries
    @type relocate_osx_binaries: bool
    @cvar strip_excludes: files that won't be stripped
    @type strip_excludes: list
    @cvar strip: strip binaries for this package
    @type strip: bool
    @cvar strip_dirs: directories to strip
    @type strip_dirs: list
    @cvar resources_license: filename of the .txt license file
    @type resources_license: str
    @cvar resources_license_unwrapped: filename of the .txt license file
                                       withouth the 80 chars wrapping
    @type resources_license_unwrapped: str
    @cvar resources_license_rtf: filename of .rtf license file
    @type resources_license_rtf: str
    @cvar resources_icon: filename of the .ico icon
    @type resources_icon: str
    @cvar resources_icon_icns: filename of the .icsn icon
    @type resources_icon_icns: str
    @cvar resources_backgound = filename of the background image
    @type resources_backgound = str
    @cvar resources_preinstall = filename for the pre-installation script
    @type resources_preinstall = str
    @cvar resources_postinstall = filename for the post-installation script
    @type resources_postinstall = str
    @cvar resources_postremove = filename for the post-remove script
    @type resources_postremove = str
    '''
    name = 'default'
    shortdesc = 'default'
    longdesc = 'default'
    version = '1.0'
    codename = None
    org = 'default'
    uuid = None
    license = License.GPL
    vendor = 'default'
    url = 'default'
    ignore_package_prefix = False
    sys_deps = None
    sys_deps_devel = None
    relocate_osx_binaries = ['lib', 'bin', 'libexec']
    strip = False
    strip_dirs = ['bin', 'lib']
    strip_excludes = []
    resources_license = 'license.txt'
    resources_license_unwrapped = 'license_unwrapped.txt'
    resources_license_rtf = 'license.txt'
    resources_icon = 'icon.ico'
    resources_icon_icns = 'icon.icns'
    resources_background = 'background.png'
    resources_preinstall = 'preinstall'
    resources_postinstall = 'postinstall'
    resources_postremove = 'postremove'
    conflicts = ''

    def __init__(self, config, store):
        if self.sys_deps is None:
            self.sys_deps = {}
        if self.sys_deps_devel is None:
            self.sys_deps_devel = {}
        self.config = config
        self.store = store
        self.package_mode = PackageType.RUNTIME

    def prepare(self):
        '''
        Can be overrided by subclasses to modify conditionally the package
        '''
        pass

    def load_files(self):
        pass

    def package_dir(self):
        '''
        Gets the directory path where this package is stored

        @return: directory path
        @rtype: str
        '''
        return os.path.dirname(self.__file__)

    def relative_path(self, path):
        '''
        Gets a path relative to the package's directory

        @return: absolute path relative to the pacakge's directory
        @rtype: str
        '''
        return os.path.abspath(os.path.join(self.package_dir(), path))

    def files_list(self):
        raise NotImplemented("'files_list' must be implemented by subclasses")

    def devel_files_list(self):
        raise NotImplemented("'devel_files_list' must be implemented by "
                             "subclasses")

    def all_files_list(self):
        raise NotImplemented("'all_files_list' must be implemented by "
                             "subclasses")

    def pre_package(self):
        pass

    def post_package(self, paths):
        pass

    def sign(self, path):
        '''
        Sign the specified path.
        It's expected to sign in-place
        '''
        pass

    def set_mode(self, package_type):
        self.package_mode = package_type

    def get_install_dir(self):
        try:
            return self.install_dir[self.config.target_platform]
        except:
            return self.config.install_dir

    def get_sys_deps(self, package_mode=None):
        package_mode = package_mode or self.package_mode
        if package_mode == PackageType.RUNTIME:
            sys_deps = self.sys_deps
        if package_mode == PackageType.DEVEL:
            sys_deps = self.sys_deps_devel

        if self.config.target_distro_version in sys_deps:
            return sys_deps[self.config.target_distro_version]
        if self.config.target_distro in sys_deps:
            return sys_deps[self.config.target_distro]
        return []

    def identifier(self):
        return '%s.%s.%s' % (self.org, self.config.target_arch, self.name)

    def __str__(self):
        return self.name

    def __getattribute__(self, name):
        attr = object.__getattribute__(self, name)
        # Return relative path for resources
        if name.startswith('resources'):
            if attr is not None:
                attr = self.relative_path(attr)
        elif name == 'name':
            attr += self.package_mode
        elif name == 'shortdesc':
            if self.package_mode == PackageType.DEVEL:
                attr += ' (Development Files)'
        elif name == 'uuid':
            if self.package_mode == PackageType.DEVEL:
                if attr is not None:
                    # Used the change the upgrade code for the devel package
                    uuid = list(attr)
                    if uuid[0] != '0':
                        uuid[0] = '0'
                    else:
                        uuid[0] = '1'
                    attr = ''.join(uuid)
        return attr


class Package(PackageBase):
    '''
    Describes a set of files to produce disctribution packages for the
    different target platforms. It provides the first level of packaging
    allowing to create modular installers by aggregating several of them.

    On Windows it will create a Merge Module (.msm) that can be easilly
    integrated in an installer (.msi).

    On OS X, it will produce a Package (.pkg) that can be integrated
    in a MetaPackager.

    On Linux it will create regular distribution packages such as a .deb on
    Debian or a .rpm on RedHat

    @cvar deps: list of packages dependencies
    @type deps: list
    @cvar files: list of files included in this package
    @type files: list
    @cvar platform_files: dict of platform files included in this package
    @type platform_files: dict
    @cvar files_devel: list of devel files included in this package
    @type files_devel: list
    @cvar platform_files_devel: dict of platform devel files included in
                                this package
    @type platform_files_Devel: dict
    @cvar osx_framework_library: name and link for the Framework library
    @type osx_framework_library: tuple
    '''

    deps = None
    files = None
    platform_files = None
    files_devel = None
    platform_files_devel = None
    osx_framework_library = None

    def __init__(self, config, store, cookbook):
        if self.deps is None:
            self.deps = []
        if self.files is None:
            self.files = []
        if self.files_devel is None:
            self.files_devel = []
        if self.platform_files is None:
            self.platform_files = {}
        if self.platform_files_devel is None:
            self.platform_files_devel = {}
        PackageBase.__init__(self, config, store)
        self.cookbook = cookbook

    def load_files(self):
        self._files = self.files + \
                self.platform_files.get(self.config.target_platform, [])
        self._files_devel = self.files_devel + \
                self.platform_files_devel.get(self.config.target_platform, [])
        self._parse_files()

    def recipes_dependencies(self):
        deps = [x.split(':')[0] for x in self._files]
        deps.extend([x.split(':')[0] for x in self._files_devel])
        for name in self.deps:
            p = self.store.get_package(name)
            deps += p.recipes_dependencies()
        return deps

    def recipes_licenses(self):
        return self._list_licenses(self._recipes_files)

    def devel_recipes_licenses(self):
        licenses = self._list_licenses(self._recipes_files_devel)
        for recipe_name, categories in self._recipes_files.iteritems():
            # also add development licenses for recipe from which used the
            # 'libs' category
            if len(categories) == 0 or FilesProvider.LIBS_CAT in categories:
                r = self.cookbook.get_recipe(recipe_name)
                if recipe_name in licenses:
                    licenses[recipe_name].update(
                            r.list_licenses_by_categories(categories))
                else:
                    licenses[recipe_name] = \
                            r.list_licenses_by_categories(categories)
        return licenses

    def files_list(self):
        files = []
        for recipe_name, categories in self._recipes_files.iteritems():
            recipe = self.cookbook.get_recipe(recipe_name)
            if len(categories) == 0:
                rfiles = recipe.dist_files_list()
            else:
                rfiles = recipe.files_list_by_categories(categories)
            files.extend(rfiles)
        return sorted(files)

    def devel_files_list(self):
        files = []
        for recipe, categories in self._recipes_files.iteritems():
            # only add development files for recipe from which used the 'libs'
            # category
            if len(categories) == 0 or FilesProvider.LIBS_CAT in categories:
                rfiles = self.cookbook.get_recipe(recipe).devel_files_list()
                files.extend(rfiles)
        for recipe, categories in self._recipes_files_devel.iteritems():
            recipe = self.cookbook.get_recipe(recipe)
            if not categories:
                rfiles = recipe.devel_files_list()
            else:
                rfiles = recipe.files_list_by_categories(categories)
            files.extend(rfiles)
        return sorted(files)

    def all_files_list(self):
        files = self.files_list()
        files.extend(self.devel_files_list())
        return sorted(files)

    def _parse_files(self):
        self._recipes_files = {}
        for r in self._files:
            l = r.split(':')
            self._recipes_files[l[0]] = l[1:]
        self._recipes_files_devel = {}
        for r in self._files_devel:
            l = r.split(':')
            self._recipes_files_devel[l[0]] = l[1:]

    def _list_licenses(self, recipes_files):
        licenses = {}
        for recipe_name, categories in recipes_files.iteritems():
            r = self.cookbook.get_recipe(recipe_name)
            # Package.files|files_devel|platform_files|platform_files_devel = \
            #        [recipe:category]
            #  => licenses = {recipe_name: {category: category_licenses}}
            # Package.files|files_devel|platform_files|platform_files_devel = \
            #        [recipe]
            #  => licenses = {recipe_name: {None: recipe_licenses}}
            licenses[recipe_name] = r.list_licenses_by_categories(categories)
        return licenses


class MetaPackage(PackageBase):
    '''
    Group of L{cerbero.packages.package.Package} used to build a a modular
    installer package.

    On Windows it will result in a .msi installer that aggregates
    Merge Modules created from a L{cerbero.packages.package.Package}.

    On OS X it will result in a MetaPackage that aggreates .pkg packages
    created a L{cerbero.packages.package.Package}.

    On Linux it will result in in rpm and deb meta-packages, whith the packages
    created as dependencies.

    @cvar packages: list of packages grouped in this meta package
    @type packages: list
    @cvar platform_packages: list of platform packages
    @type platform_packages: dict
    @cvar root_env_var: name of the environment variable with the prefix
    @type root_env_var: str
    @cvar sdk_version: SDK version. This version will be used for the SDK
                       versionning and can defer from the installer one.
    @type sdk_version: str
    @cvar resources_wix_installer: wix installer template file
    @type resources_wix_installer: string
    @cvar resources_distribution: Distribution XML template file
    @type resources_wix_installer: string
    @cvar user_resources: folders included in the .dmg for iOS packages
    @type user_resources: list
    '''

    packages = None
    root_env_var = 'CERBERO_SDK_ROOT'
    platform_packages = {}
    sdk_version = '1.0'
    resources_wix_installer = None
    resources_distribution = 'Distribution.xml'
    user_resources = None

    def __init__(self, config, store):
        PackageBase.__init__(self, config, store)
        if self.packages is None:
            self.packages = []
        if self.user_resources is None:
            self.user_resources = []

    def list_packages(self):
        return [p[0] for p in self.packages]

    def recipes_dependencies(self):
        deps = []
        for package in self.store.get_package_deps(self.name, True):
            deps.extend(package.recipes_dependencies())

        return remove_list_duplicates(deps)

    def files_list(self):
        return self._list_files(Package.files_list)

    def devel_files_list(self):
        return self._list_files(Package.devel_files_list)

    def all_files_list(self):
        return self._list_files(Package.all_files_list)

    def get_wix_upgrade_code(self):
        m = self.package_mode
        p = self.config.target_arch
        return self.wix_upgrade_code[m][p]

    def get_wix_registry_key(self):
        package_type = self.package_mode
        self.set_mode(PackageType.RUNTIME)
        name = self.shortdesc.replace(' ', '')
        self.set_mode(package_type)
        return 'Software\\%s\\%s' % (self.name, self.config.target_arch)

    def _list_files(self, func):
        # for each package, call the function that list files
        files = []
        for package in self.store.get_package_deps(self.name):
            files.extend(func(package))
        files.sort()
        return files

    def __getattribute__(self, name):
        if name == 'packages':
            attr = PackageBase.__getattribute__(self, name)
            ret = attr[:]
            platform_attr_name = 'platform_%s' % name
            if hasattr(self, platform_attr_name):
                platform_attr = PackageBase.__getattribute__(self,
                        platform_attr_name)
                if self.config.target_platform in platform_attr:
                    platform_list = platform_attr[self.config.target_platform]
                    ret.extend(platform_list)
            return ret
        else:
            return PackageBase.__getattribute__(self, name)


class SDKPackage(MetaPackage):
    '''
    Creates an installer for SDK's.

    On Windows the installer will add a new enviroment variable set in
    root_env_var as well as a new key in the registry so that other installers
    depending on the SDK could use them to set their environment easily and
    check wether the requirements are met in the pre-installation step.

    On OS X, the installer will create the tipical bundle structure used for
    OS X Frameworks, creating the 'Versions' and 'Current' directories for
    versionning as well as 'Headers' and 'Libraries' linking to the current
    version of the framework.

    On Linux everything just works without extra hacks ;)

    @cvar root_env_var: name of the environment variable with the prefix
    @type root_env_var: str
    @cvar osx_framework_library: (name, path) of the lib used for the Framework
    @type osx_framework_library: tuple

    '''

    root_env_var = 'CERBERO_SDK_ROOT_%(arch)s'
    osx_framework_library = None

    def __init__(self, config, store):
        MetaPackage.__init__(self, config, store)

    def get_root_env_var(self):
        return (self.root_env_var % {'arch': self.config.target_arch}).upper()



class InstallerPackage(MetaPackage):
    '''
    Creates an installer for a target SDK to extend it.

    @cvar sdk_package: name of the required SDK
    @type sdk_package: str
    '''

    sdk_package = None

    def __init__(self, config, store):
        MetaPackage.__init__(self, config, store)

    def get_wix_registry_key(self):
        if self.sdk_package is None:
            raise FatalError("sdk_package not set for package " + self.name)
        sdk_package = self.store.get_package(self.sdk_package)
        return sdk_package.get_wix_registry_key()


class AppExtensionPackage(Package):
    '''
    Creates an installer to extend an application.

    @cvar app_package: application package name
    @type app_package: str
    '''

    app_package = None
    resources_wix_installer = None
    resources_info_plist = 'Info.plist'
    resources_distribution = 'distribution.xml'
    _app = None

    def __init__(self, config, store, cookbook):
        Package.__init__(self, config, store, cookbook)
        self.title = self.name
        self.deps.append(self.app_package)

    def get_wix_upgrade_code(self):
        m = self.package_mode
        p = self.config.target_arch
        return self.wix_upgrade_code[m][p]

    def get_wix_registry_key(self):
        if self.app_package is None:
            raise FatalError("app_package not set for package " + self.name)
        self._fetch_app()
        return self._app.get_wix_registry_key()

    def recipes_dependencies(self):
        return [x.split(':')[0] for x in self.files]

    def get_app_dep(self):
        self._fetch_app()
        return self._app

    def _fetch_app(self):
        if not self._app:
            self._app = self.store.get_package(self.app_package)


class App(PackageBase):
    '''
    Create packages for applications.
    An App package will not include development files and binaries could
    be stripped when required. The App packager will not create a development
    version.
    On linux it will work in the same way as a MetaPackage, creating a package
    with the application's recipe files and adding packages dependencies to be
    managed by the distribution's package manager.
    On OS X and Windows, the dependencies could be embeded in the installer
    itself, creating an Application bundle on OS X and main menu shortcuts on
    Windows, relocating the binaries properly.

    @cvar app_name: Name used for the application
    @type app_name: str
    @cvar app_recipe: recipe that builds the application project
    @type app_recipe: str
    @cvar app_version: major version for the application
    @type app_version: str
    @cvar deps: list of packages dependencies
    @type deps: list
    @cvar embed_deps: include dependencies in the final package
    @type embed_deps: boolean
    @cvar commands: a list of with the application commands. The first will be
                    used for the main executable
    @type command: list
    @cvar wrapper: suffix filename for the main executable wrapper
    @type wrapper: str
    @cvar external_pkgs: external packages (.msm or .pkg) to include in the installer
    @type external_pkgs: list
    @cvar resources_info_plist: Info.plist template file
    @type resources_info_plist: string
    @cvar resources_distribution: Distribution XML template file
    @type resources_distribution: Distribution XML template file
    @cvar osx_resources: Extra files to include in the bundle's Resources
    @type osx_resources: list
    @cvar osx_create_dmg: Packages the app in a dmg
    @type osx_create_dmg: bool
    @cvar osx_create_pkg: Packages the app in a pkg
    @type osx_create_pkg: bool
    '''

    app_name = None
    app_recipe = None
    app_version = None
    embed_deps = True
    deps = None
    commands = []  # list of tuples ('CommandName', path/to/binary')
    wrapper = 'app_wrapper.tpl'
    resources_wix_bundle = None
    resources_wix_installer = None
    resources_info_plist = 'Info.plist'
    resources_distribution = 'distribution.xml'
    osx_create_dmg = True
    osx_create_pkg = True
    osx_resources = None

    def __init__(self, config, store, cookbook):
        PackageBase.__init__(self, config, store)
        if self.deps is None:
            self.deps = []
        if self.app_version is None:
            self.app_version = self.version
        if self.commands is None:
            self.commands = []
        if self.osx_resources is None:
            self.osx_resources = []
        self.cookbook = cookbook
        self._app_recipe = self.cookbook.get_recipe(self.app_recipe)
        self.title = self.name

    def recipes_dependencies(self):
        deps = []
        for dep in self.deps:
            package = self.store.get_package(dep)
            deps.extend(package.recipes_dependencies())
        if self.app_recipe is not None:
            deps.append(self.app_recipe)
        return list(set(deps))

    def files_list(self):
        # for each package, call the function that list files
        files = []
        if self.embed_deps:
            packages_deps = [self.store.get_package(x) for x in self.deps]
            for package in packages_deps:
                packages_deps.extend(self.store.get_package_deps(package))
            packages_deps = list(set(packages_deps))
            for package in packages_deps:
                files.extend(package.files_list())
            # Also include all the libraries provided by the recipes we depend
            # on.
            for recipe in self.cookbook.list_recipe_deps(self.app_recipe):
                files.extend(recipe.libraries())

        files.extend(self._app_recipe.files_list())
        files.sort()
        return files

    def devel_files_list(self):
        return []

    def all_files_list(self):
        return self.files_list()

    def recipes_licenses(self):
        # FIXME
        return {}

    def devel_recipes_licenses(self):
        # FIXME
        return {}

    def get_wix_upgrade_code(self):
        m = self.package_mode
        p = self.config.target_arch
        return self.wix_upgrade_code[m][p]

    def get_wix_registry_key(self):
        return 'Software\\%s\\%s\\%s' % (self.name, self.app_version, self.config.target_arch)

    def get_commands(self):
        return self.commands.get(self.config.target_platform, [])

    def get_wrapper(self, cmd, wrapper=None):
        if self.config.target_platform == Platform.WINDOWS:
            platform = 'win'
        else:
            platform = 'unix'

        if wrapper is not None:
            wrapper_file = self.relative_path('%s_%s' % (platform, wrapper))
        else:
            wrapper_file = os.path.join(self.config.data_dir, 'templates',
                    '%s_%s' % (self.wrapper, platform))

        if not os.path.exists(wrapper_file):
            return None

        with open(wrapper_file, 'r') as f:
            content = f.read()
            content = content % {'prefix': self.config.prefix,
                                 'py_prefix': self.config.py_prefix,
                                 'cmd': self.config.prefix}

        return content

    def __getattribute__(self, name):
        if name == 'deps':
            attr = PackageBase.__getattribute__(self, name)
            if attr is None:
                return attr
            ret = attr[:]
            platform_attr_name = 'platform_%s' % name
            if hasattr(self, platform_attr_name):
                platform_attr = PackageBase.__getattribute__(self,
                        platform_attr_name)
                if self.config.target_platform in platform_attr:
                    platform_list = platform_attr[self.config.target_platform]
                    ret.extend(platform_list)
            return ret
        else:
            return PackageBase.__getattribute__(self, name)
