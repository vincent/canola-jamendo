# Canola2 Jamendo Plugin
# Authors: Vincent Lark <vincent.lark@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Additional permission under GNU GPL version 3 section 7
#
# If you modify this Program, or any covered work, by linking or combining it
# with Canola2 and its core components (or a modified version of any of those),
# containing parts covered by the terms of Instituto Nokia de Tecnologia End
# User Software Agreement, the licensors of this Program grant you additional
# permission to convey the resulting work.

import os
import glob
import time
import string

from terra.core.plugin_prefs import PluginPrefs
from terra.core.threaded_func import ThreadedFunction

COVER_CACHE_SIZE = 100 # keep 100 covers


def normalize_path(value):
    special_table = string.maketrans('!@#$%*=+-[]{}:?<>,|/\\;~"',
                                     '                        ')
    value = value.translate(special_table)
    value = " ".join(value.split())
    return value


def get_cover_path():
    prefs = PluginPrefs("settings")
    try:
        path = prefs["lastfm_cover_path"]
    except KeyError:
        path = os.path.join(os.path.expanduser("~"),
                            ".canola", "lastfm", "covers")

    if not os.path.exists(path):
        os.makedirs(path)

    return path


def remove_old_covers(cover_path):
    """Remove old covers based on last access time."""
    lst = []
    nw = time.time()

    filelist = glob.glob(os.path.join(cover_path, "*.jpg"))

    if len(filelist) <= COVER_CACHE_SIZE:
        return

    for filepath in filelist:
        st = os.stat(filepath)
        lst.append((filepath, nw - st.st_atime))

    lst.sort(lambda a, b: int(a[1]) - int(b[1]))

    for filepath, lifetime in lst[COVER_CACHE_SIZE:]:
        os.unlink(filepath)


# Remove old covers on module loading
cover_path = get_cover_path()
ThreadedFunction(None, remove_old_covers, cover_path).start()
