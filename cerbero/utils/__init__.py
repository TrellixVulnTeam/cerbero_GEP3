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
import sys
try:
    import sysconfig
except:
    from distutils import sysconfig
try:
    import xml.etree.cElementTree as etree
except ImportError:
    from lxml import etree
from distutils.version import StrictVersion
import gettext
import platform as pplatform
import re
import inspect
import hashlib
from pathlib import Path
from functools import lru_cache
import asyncio
from collections.abc import Iterable
import threading

from cerbero.enums import Platform, Architecture, Distro, DistroVersion
from cerbero.errors import FatalError
from cerbero.utils import messages as m

_ = gettext.gettext
N_ = lambda x: x
TEXTCHARS = bytearray(set([7,8,9,10,12,13,27]) | set(range(0x20, 0x100)) - set([0x7f]))

class ArgparseArgument(object):

    def __init__(self, *name, **kwargs):
        self.name = name
        self.args = kwargs

    def add_to_parser(self, parser):
        parser.add_argument(*self.name, **self.args)


def user_is_root():
        ''' Check if the user running the process is root '''
        return hasattr(os, 'getuid') and os.getuid() == 0


def determine_num_of_cpus():
    ''' Number of virtual or physical CPUs on this system '''

    # Python 2.6+
    try:
        import multiprocessing
        return multiprocessing.cpu_count()
    except (ImportError, NotImplementedError):
        return 1


def to_winpath(path):
    if path.startswith('/'):
        path = '%s:%s' % (path[1], path[2:])
    return path.replace('/', '\\')


def to_unixpath(path):
    if path[1] == ':':
        path = '/%s%s' % (path[0], path[2:])
    return path

def to_odd_cased_unixpath(path):
    if path[1] == ':':
        # from winpath
        drive_letter = path[0]
        if drive_letter.isupper():
            drive_letter = drive_letter.lower()
        else:
            drive_letter = drive_letter.upper()
        path = drive_letter + path[1:]
        path = to_unixpath(path)
    elif path[0] == '/':
        # from unixpath
        drive_letter = path[1]
        if drive_letter.isupper():
            drive_letter = drive_letter.lower()
        else:
            drive_letter = drive_letter.upper()
        path = path[0] + drive_letter + path[2:]
    return path

def to_winepath(path):
        path = path.replace('/', '\\\\')
        # wine maps the filesystem root '/' to 'z:\'
        path = 'z:\\%s' % path
        return path


def fix_winpath(path):
    return path.replace('\\', '/')


def windows_arch():
    """
    Detecting the 'native' architecture of Windows is not a trivial task. We
    cannot trust that the architecture that Python is built for is the 'native'
    one because you can run 32-bit apps on 64-bit Windows using WOW64 and
    people sometimes install 32-bit Python on 64-bit Windows.
    """
    # These env variables are always available. See:
    # https://msdn.microsoft.com/en-us/library/aa384274(VS.85).aspx
    # https://blogs.msdn.microsoft.com/david.wang/2006/03/27/howto-detect-process-bitness/
    arch = os.environ.get('PROCESSOR_ARCHITEW6432', '').lower()
    if not arch:
        # If this doesn't exist, something is messing with the environment
        try:
            arch = os.environ['PROCESSOR_ARCHITECTURE'].lower()
        except KeyError:
            raise FatalError(_('Unable to detect Windows architecture'))
    return arch

def system_info():
    '''
    Get the sysem information.
    Return a tuple with the platform type, the architecture and the
    distribution
    '''
    # Get the platform info
    platform = os.environ.get('OS', '').lower()
    if not platform:
        platform = sys.platform
    if platform.startswith('win'):
        platform = Platform.WINDOWS
    elif platform.startswith('darwin'):
        platform = Platform.DARWIN
    elif platform.startswith('linux'):
        platform = Platform.LINUX
    else:
        raise FatalError(_("Platform %s not supported") % platform)

    # Get the architecture info
    if platform == Platform.WINDOWS:
        arch = windows_arch()
        if arch in ('x64', 'amd64'):
            arch = Architecture.X86_64
        elif arch == 'x86':
            arch = Architecture.X86
        else:
            raise FatalError(_("Windows arch %s is not supported") % arch)
    else:
        uname = os.uname()
        arch = uname[4]
        if arch == 'x86_64':
            arch = Architecture.X86_64
        elif arch.endswith('86'):
            arch = Architecture.X86
        elif arch.startswith('armv7'):
            arch = Architecture.ARMv7
        elif arch.startswith('arm'):
            arch = Architecture.ARM
        else:
            raise FatalError(_("Architecture %s not supported") % arch)

    # Get the distro info
    if platform == Platform.LINUX:
        if sys.version_info >= (3, 8, 0):
            try:
                import distro
            except ImportError:
                print('''Python >= 3.8 detected and the 'distro' python package was not found.
Please install the 'python3-distro' or 'python-distro' package from your linux package manager or from pypi using pip.
Terminating.''', file=sys.stderr)
                sys.exit(1)
            d = distro.linux_distribution()
        else:
            d = pplatform.linux_distribution()

        if d[0] == '' and d[1] == '' and d[2] == '':
            if os.path.exists('/etc/arch-release'):
                # FIXME: the python2.7 platform module does not support Arch Linux.
                # Mimic python3.4 platform.linux_distribution() output.
                d = ('arch', 'Arch', 'Linux')
            elif os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r') as f:
                    if 'ID="amzn"\n' in f.readlines():
                        d = ('RedHat', 'amazon', '')
                    else:
                        f.seek(0, 0)
                        for line in f:
                            # skip empty lines and comment lines
                            if line.strip() and not line.lstrip().startswith('#'):
                                k,v = line.rstrip().split("=")
                                if k == 'NAME':
                                    name = v.strip('"')
                                elif k == 'VERSION_ID':
                                    version = v.strip('"')
                        d = (name, version, '');

        if d[0] in ['Ubuntu', 'debian', 'Debian GNU/Linux', 'LinuxMint', 'Linux Mint']:
            distro = Distro.DEBIAN
            distro_version = d[2].lower()
            split_str = d[2].split()
            if split_str:
                distro_version = split_str[0].lower()
            if distro_version in ['maverick', 'isadora']:
                distro_version = DistroVersion.UBUNTU_MAVERICK
            elif distro_version in ['lucid', 'julia']:
                distro_version = DistroVersion.UBUNTU_LUCID
            elif distro_version in ['natty', 'katya']:
                distro_version = DistroVersion.UBUNTU_NATTY
            elif distro_version in ['oneiric', 'lisa']:
                distro_version = DistroVersion.UBUNTU_ONEIRIC
            elif distro_version in ['precise', 'maya']:
                distro_version = DistroVersion.UBUNTU_PRECISE
            elif distro_version in ['quantal', 'nadia']:
                distro_version = DistroVersion.UBUNTU_QUANTAL
            elif distro_version in ['raring', 'olivia']:
                distro_version = DistroVersion.UBUNTU_RARING
            elif distro_version in ['saucy', 'petra']:
                distro_version = DistroVersion.UBUNTU_SAUCY
            elif distro_version in ['trusty', 'qiana', 'rebecca']:
                distro_version = DistroVersion.UBUNTU_TRUSTY
            elif distro_version in ['utopic']:
                distro_version = DistroVersion.UBUNTU_UTOPIC
            elif distro_version in ['vivid']:
                distro_version = DistroVersion.UBUNTU_VIVID
            elif distro_version in ['wily']:
                distro_version = DistroVersion.UBUNTU_WILY
            elif distro_version in ['xenial', 'sarah', 'serena', 'sonya', 'sylvia']:
                distro_version = DistroVersion.UBUNTU_XENIAL
            elif distro_version in ['artful']:
                distro_version = DistroVersion.UBUNTU_ARTFUL
            elif distro_version in ['bionic', 'tara', 'tessa', 'tina', 'tricia']:
                distro_version = DistroVersion.UBUNTU_BIONIC
            elif distro_version in ['cosmic']:
                distro_version = DistroVersion.UBUNTU_COSMIC
            elif distro_version in ['disco']:
                distro_version = DistroVersion.UBUNTU_DISCO
            elif distro_version in ['eoan']:
                distro_version = DistroVersion.UBUNTU_EOAN
            elif distro_version in ['focal', 'ulyana', 'ulyssa', 'uma']:
                distro_version = DistroVersion.UBUNTU_FOCAL
            elif d[1].startswith('6.'):
                distro_version = DistroVersion.DEBIAN_SQUEEZE
            elif d[1].startswith('7.') or d[1].startswith('wheezy'):
                distro_version = DistroVersion.DEBIAN_WHEEZY
            elif d[1].startswith('8.') or d[1].startswith('jessie'):
                distro_version = DistroVersion.DEBIAN_JESSIE
            elif d[1].startswith('9.') or d[1].startswith('stretch'):
                distro_version = DistroVersion.DEBIAN_STRETCH
            elif d[1].startswith('10.') or d[1].startswith('buster'):
                distro_version = DistroVersion.DEBIAN_BUSTER
            elif d[0] in ['Ubuntu']:
                distro_version = "ubuntu_{number}_{name}".format(number=d[1].replace('.', '_'), name=distro_version)
            else:
                raise FatalError("Distribution '%s' not supported" % str(d))
        elif d[0] in ['RedHat', 'Fedora', 'CentOS', 'Red Hat Enterprise Linux Server', 'CentOS Linux']:
            distro = Distro.REDHAT
            if d[1] == '16':
                distro_version = DistroVersion.FEDORA_16
            elif d[1] == '17':
                distro_version = DistroVersion.FEDORA_17
            elif d[1] == '18':
                distro_version = DistroVersion.FEDORA_18
            elif d[1] == '19':
                distro_version = DistroVersion.FEDORA_19
            elif d[1] == '20':
                distro_version = DistroVersion.FEDORA_20
            elif d[1] == '21':
                distro_version = DistroVersion.FEDORA_21
            elif d[1] == '22':
                distro_version = DistroVersion.FEDORA_22
            elif d[1] == '23':
                distro_version = DistroVersion.FEDORA_23
            elif d[1] == '24':
                distro_version = DistroVersion.FEDORA_24
            elif d[1] == '25':
                distro_version = DistroVersion.FEDORA_25
            elif d[1] == '26':
                distro_version = DistroVersion.FEDORA_26
            elif d[1] == '27':
                distro_version = DistroVersion.FEDORA_27
            elif d[1] == '28':
                distro_version = DistroVersion.FEDORA_28
            elif d[1] == '29':
                distro_version = DistroVersion.FEDORA_29
            elif d[1] == '6' or d[1].startswith('6.'):
                distro_version = DistroVersion.REDHAT_6
            elif d[1] == '7' or d[1].startswith('7.'):
                distro_version = DistroVersion.REDHAT_7
            elif d[1] == '8' or d[1].startswith('8.'):
                distro_version = DistroVersion.REDHAT_8
            elif d[1] == 'amazon':
                distro_version = DistroVersion.AMAZON_LINUX
            else:
                # FIXME Fill this
                raise FatalError("Distribution '%s' not supported" % str(d))
        elif d[0].strip() in ['openSUSE']:
            distro = Distro.SUSE
            if d[1] == '42.2':
                distro_version = DistroVersion.OPENSUSE_42_2
            elif d[1] == '42.3':
                distro_version = DistroVersion.OPENSUSE_42_3
            else:
                # FIXME Fill this
                raise FatalError("Distribution OpenSuse '%s' "
                                 "not supported" % str(d))
        elif d[0].strip() in ['openSUSE Tumbleweed']:
            distro = Distro.SUSE
            distro_version = DistroVersion.OPENSUSE_TUMBLEWEED
        elif d[0].strip() in ['arch', 'Arch Linux']:
            distro = Distro.ARCH
            distro_version = DistroVersion.ARCH_ROLLING
        elif d[0].strip() in ['Gentoo Base System']:
            distro = Distro.GENTOO
            distro_version = DistroVersion.GENTOO_VERSION
        else:
            raise FatalError("Distribution '%s' not supported" % str(d))
    elif platform == Platform.WINDOWS:
        distro = Distro.WINDOWS
        win32_ver = pplatform.win32_ver()[0]
        dmap = {'xp': DistroVersion.WINDOWS_XP,
                'vista': DistroVersion.WINDOWS_VISTA,
                '7': DistroVersion.WINDOWS_7,
                'post2008Server': DistroVersion.WINDOWS_8,
                '8': DistroVersion.WINDOWS_8,
                'post2012Server': DistroVersion.WINDOWS_8_1,
                '8.1': DistroVersion.WINDOWS_8_1,
                '10': DistroVersion.WINDOWS_10}
        if win32_ver in dmap:
            distro_version = dmap[win32_ver]
        else:
            raise FatalError("Windows version '%s' not supported" % win32_ver)
    elif platform == Platform.DARWIN:
        distro = Distro.OS_X
        ver = pplatform.mac_ver()[0]
        if ver.startswith('10.15'):
            distro_version = DistroVersion.OS_X_CATALINA
        elif ver.startswith('10.14'):
            distro_version = DistroVersion.OS_X_MOJAVE
        elif ver.startswith('10.13'):
            distro_version = DistroVersion.OS_X_HIGH_SIERRA
        elif ver.startswith('10.12'):
            distro_version = DistroVersion.OS_X_SIERRA
        elif ver.startswith('10.11'):
            distro_version = DistroVersion.OS_X_EL_CAPITAN
        elif ver.startswith('10.10'):
            distro_version = DistroVersion.OS_X_YOSEMITE
        elif ver.startswith('10.9'):
            distro_version = DistroVersion.OS_X_MAVERICKS
        elif ver.startswith('10.8'):
            distro_version = DistroVersion.OS_X_MOUNTAIN_LION
        else:
            raise FatalError("Mac version %s not supported" % ver)

    num_of_cpus = determine_num_of_cpus()

    return platform, arch, distro, distro_version, num_of_cpus


def validate_packager(packager):
    # match packager in the form 'Name <email>'
    expr = r'(.*\s)*[<]([a-zA-Z0-9+_\-\.]+@'\
        '[0-9a-zA-Z][.-0-9a-zA-Z]*.[a-zA-Z]+)[>]$'
    return bool(re.match(expr, packager))


def copy_files(origdir, destdir, files, extensions, target_platform):
    for f in files:
        f = f % extensions
        install_dir = os.path.dirname(os.path.join(destdir, f))
        if not os.path.exists(install_dir):
            os.makedirs(install_dir)
        if destdir[1] == ':':
            # windows path
            relprefix = to_unixpath(destdir)[2:]
        else:
            relprefix = destdir[1:]
        orig = os.path.join(origdir, relprefix, f)
        dest = os.path.join(destdir, f)
        m.action("copying %s to %s" % (orig, dest))
        try:
            shutil.copy(orig, dest)
        except IOError:
            m.warning("Could not copy %s to %s" % (orig, dest))


def remove_list_duplicates(seq):
    ''' Remove list duplicates maintaining the order '''
    seen = set()
    seen_add = seen.add
    return [x for x in seq if x not in seen and not seen_add(x)]


def parse_file(filename, dict):
    if '__file__' not in dict:
        dict['__file__'] = filename
    try:
        exec(compile(open(filename).read(), filename, 'exec'), dict)
    except Exception as ex:
        import traceback
        traceback.print_exc()
        raise ex


def escape_path(path):
    path = path.replace('\\', '/')
    path = path.replace('(', '\\\(').replace(')', '\\\)')
    path = path.replace(' ', '\\\\ ')
    return path


def get_wix_prefix():
    if 'WIX' in os.environ:
        wix_prefix = os.path.join(os.environ['WIX'], 'bin')
    else:
        wix_prefix = 'C:/Program Files%s/Windows Installer XML v3.5/bin'
        if not os.path.exists(wix_prefix):
            wix_prefix = wix_prefix % ' (x86)'
    if not os.path.exists(wix_prefix):
        raise FatalError("The required packaging tool 'WiX' was not found")
    return escape_path(to_unixpath(wix_prefix))

def add_system_libs(config, new_env):
    '''
    Add /usr/lib/pkgconfig to PKG_CONFIG_PATH so the system's .pc file
    can be found.
    '''
    arch = config.target_arch
    libdir = 'lib'

    if arch == Architecture.X86_64:
        if config.distro == Distro.REDHAT or config.distro == Distro.SUSE:
            libdir = 'lib64'

    sysroot = '/'
    if config.sysroot:
        sysroot = config.sysroot

    search_paths = [os.environ['PKG_CONFIG_LIBDIR'],
        os.path.join(sysroot, 'usr', libdir, 'pkgconfig'),
        os.path.join(sysroot, 'usr/share/pkgconfig')]

    if config.target_distro == Distro.DEBIAN:
        host = None
        if arch == Architecture.ARM:
            host = 'arm-linux-gnueabi'
        elif arch == Architecture.ARM64:
            host = 'aarch64-linux-gnu'
        elif arch == Architecture.X86:
            host = 'i386-linux-gnu'
        elif Architecture.is_arm(arch):
            host = 'arm-linux-gnueabihf'
        else:
            host = '%s-linux-gnu' % arch

        search_paths.append(os.path.join(sysroot, 'usr/lib/%s/pkgconfig' % host))

    new_env['PKG_CONFIG_PATH'] = ':'.join(search_paths)

    search_paths = [os.environ.get('ACLOCAL_PATH', ''),
        os.path.join(sysroot, 'usr/share/aclocal')]
    new_env['ACLOCAL_PATH'] = ':'.join(search_paths)

def needs_xcode8_sdk_workaround(config):
    '''
    Returns whether the XCode 8 clock_gettime, mkostemp, getentropy workaround
    from https://bugzilla.gnome.org/show_bug.cgi?id=772451 is needed

    These symbols are only available on macOS 10.12+ and iOS 10.0+
    '''
    if config.target_platform == Platform.DARWIN:
        if StrictVersion(config.min_osx_sdk_version) < StrictVersion('10.12'):
            return True
    elif config.target_platform == Platform.IOS:
        if StrictVersion(config.ios_min_version) < StrictVersion('10.0'):
            return True
    return False

def _qmake_or_pkgdir(qmake):
    qmake_path = Path(qmake)
    if not qmake_path.is_file():
        m.warning('QMAKE={!r} does not exist'.format(str(qmake_path)))
        return (None, None)
    pkgdir = (qmake_path.parent.parent / 'lib/pkgconfig')
    if pkgdir.is_dir():
        return (pkgdir.as_posix(), qmake_path.as_posix())
    return (None, qmake_path.as_posix())

def detect_qt5(platform, arch, is_universal):
    '''
    Returns both the path to the pkgconfig directory and the path to qmake:
    (pkgdir, qmake). If `pkgdir` could not be found, it will be None

    Returns (None, None) if nothing was found.
    '''
    path = None
    qt5_prefix = os.environ.get('QT5_PREFIX', None)
    qmake_path = os.environ.get('QMAKE', None)
    if not qt5_prefix and not qmake_path:
        return (None, None)
    if qt5_prefix and not os.path.isdir(qt5_prefix):
        m.warning('QT5_PREFIX={!r} does not exist'.format(qt5_prefix))
        return (None, None)
    if qmake_path:
        if is_universal and platform == Platform.ANDROID:
            if not qt5_prefix:
                m.warning('Please set QT5_PREFIX if you want to build '
                          'the Qt5 plugin for android-universal')
                return (None, None)
        else:
            ret = _qmake_or_pkgdir(qmake_path)
            if ret != (None, None) or not qt5_prefix:
                return ret
    # qmake path is invalid, find pkgdir or qmake from qt5 prefix
    if platform == Platform.ANDROID:
        if arch == Architecture.ARMv7:
            ret = _qmake_or_pkgdir(os.path.join(qt5_prefix, 'android_armv7/bin/qmake'))
        elif arch == Architecture.ARM64:
            ret = _qmake_or_pkgdir(os.path.join(qt5_prefix, 'android_arm64_v8a/bin/qmake'))
        elif arch == Architecture.X86:
            ret = _qmake_or_pkgdir(os.path.join(qt5_prefix, 'android_x86/bin/qmake'))
        elif arch == Architecture.X86_64:
            # Qt binaries do not ship a qmake for android_x86_64
            return (None, None)
    elif platform == Platform.DARWIN:
        if arch == Architecture.X86_64:
            ret = _qmake_or_pkgdir(os.path.join(qt5_prefix, 'clang_64/bin/qmake'))
    elif platform == Platform.IOS:
        ret = _qmake_or_pkgdir(os.path.join(qt5_prefix, 'ios/bin/qmake'))
    elif platform == Platform.LINUX:
        if arch == Architecture.X86_64:
            ret = _qmake_or_pkgdir(os.path.join(qt5_prefix, 'gcc_64/bin/qmake'))
    elif platform == Platform.WINDOWS:
        # There are several msvc and mingw toolchains to pick from, and we
        # can't pick it for the user.
        m.warning('You must set QMAKE instead of QT5_PREFIX on Windows')
        return (None, None)
    if ret == (None, None):
        m.warning('Unsupported arch {!r} on platform {!r}'.format(arch, platform))
    return ret

def replace_prefix(prefix, string, replacement='{PREFIX}'):
    '''
    Replace all possible ways of writing the prefix.
    This function replaces in a string.

    @return: replaced string
    @rtype: str

    @cvar prefix: prefix to be replaced
    @rtype: str
    @cvar string: the original string
    @rtype: str
    @cvar replacement: the placeholder to put instead of the prefix
    @rtype: str
    '''
    for p in [prefix, to_unixpath(prefix), to_winpath(prefix),
              to_winepath(prefix), to_odd_cased_unixpath(prefix),
              os.path.normpath(prefix)]:
        string = string.replace(p, replacement)
    return string

def replace_prefix_in_bytes(prefix, byte_str, replacement='{PREFIX}'):
    '''
    Replace all possible ways of writing the prefix.
    This function replaces in a string.

    @return: replaced string
    @rtype: bytes

    @cvar prefix: prefix to be replaced
    @rtype: str
    @cvar byte_str: the original byte string
    @rtype: bytes
    @cvar replacement: the placeholder to put instead of the prefix
    @rtype: str
    '''
    for p in [prefix, to_unixpath(prefix), to_winpath(prefix),
              to_winepath(prefix), to_odd_cased_unixpath(prefix),
              os.path.normpath(prefix)]:
        byte_str = byte_str.replace(p.encode('utf-8'), replacement.encode('utf-8'))
    return byte_str

def is_text_file(filename):
    '''
    Check if a file is text or binary.
    This uses the same logic as file(1).
    Adapted from https://stackoverflow.com/a/7392391/1324984.
    Assume that > 99% is text
    '''
    global TEXTCHARS
    with open(filename, 'rb') as f:
        return len(f.read(1024).translate(None, TEXTCHARS)) <= 10

@lru_cache(maxsize=None)
def get_class_checksum(clazz):
    '''
    Return the SHA256 hash from the source lines of a class.
    This method uses an LRU cache to avoid calculating the same
    again and again
    '''
    sha256 = hashlib.sha256()
    lines = inspect.getsourcelines(clazz)[0]
    for line in lines:
        sha256.update(line.encode('utf-8'))
    return sha256.digest()

def get_event_loop():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # On Windows the default SelectorEventLoop is not available:
    # https://docs.python.org/3.5/library/asyncio-subprocess.html#windows-event-loop
    if sys.platform == 'win32' and \
       not isinstance(loop, asyncio.ProactorEventLoop):
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)

    # Avoid spammy BlockingIOError warnings with older python versions
    if sys.platform != 'win32' and \
       sys.version_info < (3, 8, 0):
        asyncio.set_child_watcher(asyncio.FastChildWatcher())
        asyncio.get_child_watcher().attach_loop(loop)

    return loop

def run_until_complete(tasks, max_concurrent=determine_num_of_cpus()):
    '''
    Runs one or many tasks, blocking until all of them have finished.
    @param tasks: A single Future or a list of Futures to run
    @type tasks: Future or list of Futures
    @param max_concurrent: Number of concurrent tasks to execute
    @type max_concurrent: int
    @return: the result of the asynchronous task execution (if only
             one task) or a list of all results in case of multiple
             tasks. Result is None if operation is cancelled.
    @rtype: any type or list of any types in case of multiple tasks
    '''
    if not tasks:
        return

    loop = get_event_loop()

    # We need to take into account that run_until_complete may be called from within
    # an async task. Since an event loop cannot be run within another one, we need
    # to create a new thread which will create a different loop. We wait until all those
    # tasks scheduled for the other thread finish. Only then we let the rest of the tasks
    # to continue their execution.
    if loop.is_running():
        thread = threading.Thread(target=run_until_complete, args=(tasks, max_concurrent))
        thread.start()
        return thread.join()

    try:
        if isinstance(tasks, Iterable):
            if not max_concurrent:
                result = loop.run_until_complete(asyncio.gather(*tasks))
            else:
                async def _worker(semaphore, task):
                    async with semaphore:
                        await task

                semaphore = asyncio.Semaphore(max_concurrent)
                worker_tasks = [_worker(semaphore, task) for task in tasks]
                result = loop.run_until_complete(asyncio.gather(*worker_tasks))
        else:
            result = loop.run_until_complete(tasks)
        return result
    except asyncio.CancelledError:
        return None


def use_devtoolset7_in_redhat(distro_version, recipe):
    if distro_version in [DistroVersion.REDHAT_6, DistroVersion.REDHAT_7]:
        if not os.path.isdir('/opt/rh/devtoolset-7/root/usr'):
            raise FatalError('Pakage "devtoolset-7" not found')

        recipe.set_env('PATH', '/opt/rh/devtoolset-7/root/usr/bin:%s' % os.environ['PATH'])
        recipe.set_env('LD_LIBRARY_PATH', ('/opt/rh/devtoolset-7/root/usr/lib64:/opt/rh/devtoolset-7/root/usr/lib:%s' %
                                           os.environ['LD_LIBRARY_PATH']))
