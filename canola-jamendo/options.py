# Canola2 Last.fm Plugin
# Copyright (C) 2008 Instituto Nokia de Tecnologia
# Authors: Adriano Rezende <adriano.rezende@openbossa.org>
#          Artur Duque de Souza <artur.souza@openbossa.org>
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

import ecore
import logging

from terra.core.manager import Manager
from terra.core.threaded_func import ThreadedFunction

from manager import LastfmManager
from client import HandshakeError, AuthenticationError

manager = Manager()
lastfm_manager = LastfmManager()
network = manager.get_status_notifier("Network")
ModalController = manager.get_class("Controller/Modal")
UsernamePasswordModal = manager.get_class("Widget/Settings/UsernamePasswordModal")
MixedListController = manager.get_class("Controller/Settings/Folder/MixedList")

log = logging.getLogger("plugins.canola-lastfm.options")


class OptionsController(MixedListController):
    terra_type = "Controller/Settings/Folder/InternetMedia/Lastfm"


class UserPassController(ModalController):
    terra_type = "Controller/Settings/Folder/InternetMedia/Lastfm/UserPass"

    def __init__(self, model, canvas, parent):
        ModalController.__init__(self, model, canvas, parent)

        self.parent_controller = parent
        self.model = model
        self.view = UsernamePasswordModal(parent, "Login to Last.fm",
                                          parent.view.theme,
                                          vborder=50)

        self.view.username = self.model.username
        self.view.password = self.model.password

        self.view.callback_ok_clicked = self._on_ok_clicked
        self.view.callback_cancel_clicked = self.close
        self.view.callback_escape = self.close
        self.view.show()

    def close(self):
        def cb(*ignored):
            self.parent_controller.view.list.redraw_queue()
            self.back()
        self.view.hide(end_callback=cb)

    def _on_ok_clicked(self):
        if not self.view.username or not self.view.password:
            return

        lastfm_manager.set_username(self.view.username)
        lastfm_manager.set_password(self.view.password)

        def refresh(session):
            session.login()

        def refresh_finished(exception, retval):
            def cb_close(*ignored):
                self.close()
                self.parent.killall()

            if exception is None:
                self.model.title = "Logged as %s" % \
                    lastfm_manager.get_username()

                self.view.message("You are now logged in")
                ecore.timer_add(1.5, cb_close)
            elif isinstance(exception, AuthenticationError) or \
                    isinstance(exception, HandshakeError):
                self.view.message("Login error: %s" % exception.message)
                ecore.timer_add(1.5, cb_close)
            else:
                self.view.message("Unable to connect to server."
                                  "<br>Check your connection and <br>try again.")
                ecore.timer_add(1.5, cb_close)

        self.view.message_wait("  Trying to login...")
        ThreadedFunction(refresh_finished, refresh, lastfm_manager).start()

    def delete(self):
        self.view.delete()
        self.view = None
        self.model = None
