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

from terra.core.singleton import Singleton
from terra.core.plugin_prefs import PluginPrefs

from client import Client


class JamendoManager(Singleton, Client):
    def __init__(self):
        Singleton.__init__(self)
        Client.__init__(self)

        self.prefs = PluginPrefs("jamendo")
        self.username = self.get_preference("username", "")
        self.password = self.get_preference("password", "")

    def is_logged(self):
        return self.logged

    def has_preference(self, name):
        return self.prefs.has_key(name)

    def get_preference(self, name, default=None):
        return self.prefs.get(name, default)

    def set_preference(self, name, value):
        self.prefs[name] = value
        self.prefs.save()

    def get_username(self):
        return self.username

    def set_username(self, value):
        self.username = value
        self.set_preference("username", value)

    def get_password(self):
        return self.password

    def set_password(self, value):
        self.password = value
        self.set_preference("password", value)
