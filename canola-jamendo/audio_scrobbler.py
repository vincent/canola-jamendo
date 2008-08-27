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
from time import mktime, localtime
from datetime import datetime

from Queue import Queue
from terra.core.manager import Manager
from terra.core.plugin_prefs import PluginPrefs
from terra.core.threaded_func import ThreadedFunction

from manager import LastfmManager


mger = Manager()
lastfm_manager = LastfmManager()
PlayerHook = mger.get_class("Hook/Player")
network = mger.get_status_notifier("Network")

log = logging.getLogger("plugins.canola-lastfm.scrobbler")


class AudioScrobbler(PlayerHook):
    terra_type = "Hook/Player/Audio"
    time_cons = 240
    np_time = 5
    max_cached = 200

    def __init__(self):
        PlayerHook.__init__(self)
        self._model = None
        self._timer = None
        self.start_time = None
        self._timer_paused = False
        self.prefs = PluginPrefs("lastfm")
        self.sending_submits = False
        self.pending_submits = Queue()

    def media_changed(self, model):
        """Function that is called everytime that the Player's Controller
        changes the model.
        """
        if self._timer is not None:
            self._timer.delete()
            self._timer_paused = False

        log.warning("media changed to %s" % model.title)

        self._model = model
        self._length = 0
        self.start_time = None

    def _validate_cmd(self, submit=False, length=None,
                      name=None, album=None):
        dsc = bool(submit) and "submit" or "now playing"
        name = name or self._model.name
        album = album or self._model.album
        if length is None:
            length = self._length

        if not lastfm_manager.get_username() or \
                not lastfm_manager.get_password():
            log.warning("%s ignored (user or pass empty): %s - %s" % \
                            (dsc, name, album))
            return False

        if not lastfm_manager.scrobble_enabled:
            log.warning("%s ignored (scrobble disabled): %s - %s" % \
                            (dsc, name, album))
            return False

        if lastfm_manager.session_id and not lastfm_manager.post_session_id:
            log.warning("%s ignored (no post sessiond id): %s - %s" % \
                            (dsc, name, album))
            return False

        if submit and not length:
            log.error("%s ignored (length not specified): %s - %s" % \
                          (dsc, name, album))
            return False

        log.warning("sending %s: %s - %s" % (dsc, name, album))
        return True

    def _now_playing(self):
        if self._validate_cmd() and (network and network.status > 0.0):
            ThreadedFunction(None, lastfm_manager.now_playing,
                             self._model.name, self._model.artist,
                             self._model.album, self._model.trackno,
                             self._length).start()

    def _cache_submit_send(self):
        # create offline cache if not exists
        if not self.prefs.has_key('submit_cache'):
            self.prefs['submit_cache'] = []

        # refresh offline cache from queue
        while self.pending_submits.qsize() > 0:
            if len(self.prefs['submit_cache']) >= self.max_cached:
                self.prefs['submit_cache'] = \
                    self.prefs['submit_cache'][-self.max_cached + 1:]
            args = self.pending_submits.get()
            self.prefs['submit_cache'].append(args)

        # save to file
        self.prefs.save()

        # nothing to do
        if not self.prefs['submit_cache']:
            return

        # send all cached submits
        for args in self.prefs['submit_cache']:
            if self._validate_cmd(submit=True, length=args[4],
                                  name=args[0], album=args[2]):
                try:
                    lastfm_manager.submit(*args)
                except Exception, e:
                    log.error("error on submit %s" % e.message)
            self.prefs['submit_cache'] = self.prefs['submit_cache'][1:]

        # save to file
        self.prefs.save()

    def _submit(self):
        args = (self._model.name or "", self._model.artist,
                self._model.album or "", self._model.trackno,
                self._length, self.start_time)

        self.pending_submits.put(args)

        if (network and network.status > 0.0) and not self.sending_submits:
            def cb_finished(*ignored):
                self.sending_submits = False

            self.sending_submits = True
            ThreadedFunction(cb_finished, self._cache_submit_send).start()

    def create_timer(self, time, func):
        if self._timer is not None:
            self._timer.delete()
        self._start_timer = int(ecore.time_get())
        self._total_time = time
        self._timer_func = func
        self._timer = ecore.timer_add(time, func)
        return self._timer

    def pause_timer(self):
        if self._timer is None:
            return

        self._stop_timer = int(ecore.time_get())
        self._timer.stop()
        self._timer_paused = True

    def resume_timer(self):
        self._timer_paused = False
        time = self._total_time - (self._stop_timer - self._start_timer)
        self.create_timer(time, self._timer_func)

    def playing(self):
        """Function that is called everytime that the Player's Controller
        changes it's state to 'PLAYING'.
        """
        if self._timer_paused:
            self.resume_timer()

        if self.start_time is None:
            self.start_time = int(mktime(localtime()))
            self._now_playing()

    def paused(self):
        """Function that is called everytime that the Player's Controller
        changes it's state to 'PAUSED'.
        """
        self.pause_timer()

    def duration_updated(self, duration):
        """Function that is called everytime that the Player's Controller
        updates it's length.
        """
        self._length = duration

        if duration < 30:
            return
        elif duration > self.time_cons:
            time = self.time_cons
        else:
            time = duration / 2

        self.create_timer(time, self._submit)
