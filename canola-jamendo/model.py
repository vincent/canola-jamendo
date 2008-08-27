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
import time
import urllib
import urllib2
import socket
import logging

from terra.core.task import Task
from terra.core.manager import Manager
from terra.core.model import ModelFolder
from terra.utils.encoding import to_utf8
from terra.core.threaded_func import ThreadedFunction

from client import TuningError
from manager import JamendoManager
from utils import get_cover_path, normalize_path

mger = Manager()
jam_manager = JamendoManager()
network = mger.get_status_notifier("Network")
PluginDefaultIcon = mger.get_class("Icon/Plugin")
CanolaError = mger.get_class("Model/Notify/Error")
ActionModelFolder = mger.get_class("Model/Options/Action")
OptionsModelFolder = mger.get_class("Model/Options/Folder")
BaseAudioLocalModel = mger.get_class("Model/Media/Audio/Local")

log = logging.getLogger("plugins.canola-jamendo.model")

TAG_LAST_PLAYED = "last_played_songs"

(SERVICE_PERSONAL, SERVICE_SIMILAR_ARTISTS,
SERVICE_TAG, SERVICE_RADIO) = range(4)


class Icon(PluginDefaultIcon):
    terra_type = "Icon/Folder/Task/Audio/Jamendo"
    icon = "icon/main_item/jamendo"
    plugin = "jamendo"


class AudioLocalModel(BaseAudioLocalModel):
    terra_type = "Model/Media/Audio/Local/Jamendo"

    cover = None
    album = None
    rating = None
    artist = None
    playcnt = None

    def __init__(self, parent):
        BaseAudioLocalModel.__init__(self, parent)
        self.size = 0
        self.rating = None
        self.visit_time = 0
        self.view_count = 0
        self.playcount = 0
        self.local_path = None
        self.parent = parent

    def ban_track(self):
        def request(session, artist, title):
            return session.ban_track(artist, title)

        def request_finished(exception, retval):
            log.warning("track marked as banned: " + str(retval))

        log.warning("marking track as banned %s/%s" % (self.artist, self.title))
        ThreadedFunction(request_finished, request,
                         lastfm_manager, self.artist, self.title).start()

    def love_track(self):
        def request(session, artist, title):
            return session.love_track(artist, title)

        def request_finished(exception, retval):
            log.warning("track marked as loved: " + str(retval))

        log.warning("marking track as loved %s/%s" % (self.artist, self.title))
        ThreadedFunction(request_finished, request,
                         lastfm_manager, self.artist, self.title).start()

    def request_cover(self, end_callback=None):
        thumb = os.path.join(get_cover_path(),
                             "%s - %s.jpg" % (normalize_path(self.artist),
                                              normalize_path(self.title)))

        if os.path.exists(thumb):
            self.thumb = self.cover = thumb
            if end_callback:
                end_callback(self.cover)
            return

        if not self.remote_thumbnail:
            return

        def refresh(remote_url, local_path):
            try:
                urllib.urlretrieve(remote_url, local_path)
            except:
                pass
            if os.path.exists(local_path):
                return local_path
            else:
                return None

        def refresh_finished(exception, retval):
            self.thumb = self.cover = retval
            if end_callback:
                end_callback(retval)

        log.warning("requesting thumb %s" % self.remote_thumbnail)

        ThreadedFunction(refresh_finished, refresh,
                         self.remote_thumbnail, thumb).start()


class PromptModelFolder(ModelFolder):
    prompt_based = False
    prompt_title = ""
    prompt_label = ""
    prompt_value = ""
    query = None

    def __init__(self, name, parent):
        ModelFolder.__init__(self, name, parent)
        self.callback_notify = None
        self.callback_no_track_found = None

    def emit_str_notify(self, value):
        if self.callback_notify:
            self.callback_notify(CanolaError(value))


class ServiceModelFolder(PromptModelFolder):
    terra_type = "Model/Folder/Task/Audio/Jamendo/Service"

    db = mger.canola_db
    threaded_search = True

    def __init__(self, name, parent):
        PromptModelFolder.__init__(self, name, parent)
        self.changed = False
        self.callback_search_finished = None
        self.username = lastfm_manager.get_username()
        self.password = lastfm_manager.get_password()

    def reload(self):
        self.children.freeze()
        self.unload()
        self.load()
        self.children.thaw()

    def do_load(self):
        self.search()

    def search(self, end_callback=None):
        if not self.threaded_search:
            for c in self.do_search():
                self.children.append(c)
            return

        def refresh():
            return self.do_search()

        def refresh_finished(exception, retval):
            log.warning("search finished")

            if not self.is_loading:
                log.info("model is not loading")
                return

            if exception is not None:
                if type(exception) is socket.gaierror:
                    emsg = "Unable to connect to server.<br>" + \
                        "Check your connection and try again."
                elif isinstance(exception, TuningError):
                    emsg = "This radio doesn't exist or it " + \
                        "is only available for Last.fm subscribers"
                elif isinstance(exception, urllib2.URLError):
                    emsg = "Unable to resolve url. <br>" + \
                        "Check your connection and try again."
                else:
                    emsg = "An unknown error has occured.<br>" + \
                        str(exception.message)

                log.error(exception)

                if self.callback_notify:
                    self.callback_notify(CanolaError(emsg))
                return

            if not retval:
                log.error("no track found")
                if self.callback_no_track_found:
                    self.callback_no_track_found()

            for item in retval:
                self.children.append(item)

            if end_callback:
                end_callback()

            if self.callback_search_finished:
                self.callback_search_finished()

            self.inform_loaded()

        self.is_loading = True
        ThreadedFunction(refresh_finished, refresh).start()

    def do_search(self):
        raise NotImplementedError("must be implemented by subclasses")

    def update_history(self):
        raise NotImplementedError("must be implemented by subclasses")

    def parse_entry_list(self, lst):
        return [self._create_model_from_entry(c) for c in lst]

    def _create_model_from_entry(self, data):
        model = AudioLocalModel(self)

        model.id = data.mbid
        model.uri = data.url
        model.remote_uri = data.url
        model.title = data.name
        if data.album is not None:
            model.album = data.album.name
        if data.artist is not None:
            model.artist = data.artist.name
        model.playcount = data.playcount
        model.durationfm = data.duration

        # do not load no-image cover
        if not data.image or data.image.find("/noimage/cover") >= 0:
            model.remote_thumbnail = None
        else:
            model.remote_thumbnail = data.image

        return model


##############################################################################
# Remote Service Models
##############################################################################

class PlayNowModelFolder(ServiceModelFolder):
    terra_type = "Model/Folder/Task/Audio/Jamendo/Service/PlayNow"

    def __init__(self, name, parent):
        ServiceModelFolder.__init__(self, name, parent)

    def do_search(self):
        lst = lastfm_manager.get_preference(TAG_LAST_PLAYED)
        if lst is None:
            return None

        param = lst.get(lastfm_manager.get_username().lower(), None)
        if param is None:
            return None

        model_type, model_parm = param

        if model_type == SERVICE_PERSONAL:
            lastfm_manager.tune_user(model_parm, "personal")
        elif model_type == SERVICE_TAG:
            lastfm_manager.tune("lastfm://globaltags/%s" % model_parm)
        elif model_type == SERVICE_RADIO:
            lastfm_manager.tune("lastfm://group/%s" % model_parm)
        elif model_type == SERVICE_SIMILAR_ARTISTS:
            lastfm_manager.tune("lastfm://artist/%s" % model_parm)
        else:
            return None

        lst = lastfm_manager.get_xspf_tracks()
        return self.parse_entry_list(lst)

    def update_history(self):
        pass


class PersonalModelFolder(ServiceModelFolder):
    terra_type = "Model/Folder/Task/Audio/Jamendo/Service/Personal"

    def __init__(self, name, parent, username):
        ServiceModelFolder.__init__(self, name, parent)
        self.username = username

    def do_search(self):
        log.warning("searching for user radio: '%s'" % self.username)

        lastfm_manager.tune_user(self.username, "personal")
        lst = lastfm_manager.get_xspf_tracks()
        return self.parse_entry_list(lst)

    def update_history(self):
        HistoryModelFolder.insert(SERVICE_PERSONAL, self.username)


class SearchByTagModelFolder(ServiceModelFolder):
    terra_type = "Model/Folder/Task/Audio/Jamendo/Service/SearchByTag"
    prompt_based = True
    prompt_title = "Music Tagged"
    prompt_label = "Enter a global tag"
    prompt_value = ""

    def __init__(self, name, parent):
        ServiceModelFolder.__init__(self, name, parent)

    def do_search(self):
        log.warning("searching for tag: '%s'" % self.query)

        lastfm_manager.tune("lastfm://globaltags/%s" % self.query)
        lst = lastfm_manager.get_xspf_tracks()
        return self.parse_entry_list(lst)

    def update_history(self):
        HistoryModelFolder.insert(SERVICE_TAG, self.query)


class SearchByRadioModelFolder(ServiceModelFolder):
    terra_type = "Model/Folder/Task/Audio/Jamendo/Service/SearchByRadio"
    prompt_based = True
    prompt_title = "Group Radio"
    prompt_label = "Enter the group name"
    prompt_value = ""

    def __init__(self, name, parent):
        ServiceModelFolder.__init__(self, name, parent)

    def do_search(self):
        log.warning("searching for radio: '%s'" % self.query)

        lastfm_manager.tune("lastfm://group/%s" % self.query)
        lst = lastfm_manager.get_xspf_tracks()
        return self.parse_entry_list(lst)

    def update_history(self):
        HistoryModelFolder.insert(SERVICE_RADIO, self.query)


class SearchByArtistModelFolder(ServiceModelFolder):
    terra_type = "Model/Folder/Task/Audio/Lastfm/Service/SearchByArtist"
    prompt_based = True
    prompt_title = "Artist Similar to"
    prompt_label = "Enter an artist name"
    prompt_value = ""

    def __init__(self, name, parent):
        ServiceModelFolder.__init__(self, name, parent)

    def do_search(self):
        log.warning("searching for similar artists: '%s'" % self.query)

        lastfm_manager.tune("lastfm://artist/%s" % self.query)
        lst = lastfm_manager.get_xspf_tracks()
        return self.parse_entry_list(lst)

    def update_history(self):
        HistoryModelFolder.insert(SERVICE_SIMILAR_ARTISTS, self.query)


class FriendsModelFolder(ServiceModelFolder):
    terra_type = "Model/Folder/Task/Audio/Lastfm/Friends"

    def __init__(self, name, parent):
        ServiceModelFolder.__init__(self, name, parent)

    def do_search(self):
        lst = []
        username = lastfm_manager.get_username()
        for c in lastfm_manager.get_friends(username):
            lst.append(PersonalModelFolder(c.username, None, c.username))
        return lst


class NeighboursModelFolder(ServiceModelFolder):
    terra_type = "Model/Folder/Task/Audio/Lastfm/Neighbours"

    def __init__(self, name, parent):
        ServiceModelFolder.__init__(self, name, parent)

    def do_search(self):
        lst = []
        username = lastfm_manager.get_username()
        for c in lastfm_manager.get_neighbours(username):
            lst.append(PersonalModelFolder(c.username, None, c.username))
        return lst


class HistoryModelFolder(ModelFolder):
    terra_type = "Model/Folder/Task/Audio/Lastfm/History"

    db = mger.canola_db

    table_name = "lastfm_history"

    stmt_create = """CREATE TABLE IF NOT EXISTS %s
                     (
                        username    VARCHAR,
                        model_type  INTEGER,
                        model_parm  VARCHAR,
                        visit_time  INTEGER,
                        primary key(username, model_type, model_parm)
                     )""" % table_name

    stmt_insert = """INSERT INTO %s(username, model_type, model_parm, visit_time)
                     VALUES (?, ?, ?, ?)""" % table_name

    stmt_update = """UPDATE %s SET visit_time = ?
                     WHERE username = ? AND model_type = ?
                       AND model_parm = ?""" % table_name

    stmt_select_all = """SELECT model_type, model_parm
                         FROM %s
                         WHERE username = ?
                         ORDER BY visit_time DESC""" % table_name

    stmt_delete_all = """DELETE FROM %s""" % table_name

    def __init__(self, name, parent):
        ModelFolder.__init__(self, name, parent)
        self.db.execute(self.stmt_create)

    @classmethod
    def insert(cls, model_type, model_parm):
        username = lastfm_manager.get_username()

        try:
            cls.db.execute(cls.stmt_insert,
                           (username, model_type, model_parm, time.time()))
        except:
            cls.db.execute(cls.stmt_update,
                           (time.time(), username, model_type, model_parm))

        lst = lastfm_manager.get_preference(TAG_LAST_PLAYED)
        if lst is None:
            lst = {}
        lst[username.lower()] = (model_type, model_parm)
        lastfm_manager.set_preference(TAG_LAST_PLAYED, lst)

    @classmethod
    def select_model_all(cls):
        username = lastfm_manager.get_username()
        rows = cls.db.execute(cls.stmt_select_all, (username,))
        return rows

    def delete_model_all(self):
        self.db.execute(self.stmt_delete_all)

    def reload(self):
        self.children.freeze()
        self.unload()
        self.load()
        self.children.thaw()

    def do_load(self):
        del self.children[:]

        history_list = self.select_model_all()

        if not history_list:
            return

        for row in history_list:
            model_type = row[0]
            model_parm = row[1]
            self.create_model_from_type(model_type, model_parm, self)

    @classmethod
    def create_model_from_type(cls, model_type, model_parm, parent=None, name=None):
        if model_type == SERVICE_PERSONAL:
            model = PersonalModelFolder(name or ("%s's radio station" % model_parm),
                                        parent, model_parm)
        elif model_type == SERVICE_TAG:
            model = SearchByTagModelFolder(name or ("%s tag radio" % model_parm),
                                           parent)
            model.query = model_parm
        elif model_type == SERVICE_RADIO:
            model = SearchByRadioModelFolder(name or ("%s radio" % model_parm),
                                             parent)
            model.query = model_parm
        elif model_type == SERVICE_SIMILAR_ARTISTS:
            model = SearchByArtistModelFolder(name or ("%s similar artists" % model_parm),
                                              parent)
            model.query = model_parm
        else:
            return None
        model.prompt_based = False

        return model


class MainModelFolder(Task, ModelFolder):
    terra_type = "Model/Folder/Task/Audio/Lastfm"
    terra_task_type = "Task/Audio/Lastfm"

    def __init__(self, parent):
        Task.__init__(self)
        ModelFolder.__init__(self, "Last.fm", parent)

    def do_load(self):
        def refresh():
            # try to login if user/pass are not empty
            if lastfm_manager.get_username() and lastfm_manager.get_password():
                lastfm_manager.login()
            return lastfm_manager.is_logged()

        def refresh_finished(exception, retval):
            if not retval or exception:
                self.inform_loaded()
                if network and network.status > 0.0:
                    not_logged_message = "You are not logged in.<br>"\
                        "Log in on Settings > Internet media > Last.fm"
                    self.callback_info(not_logged_message)
                else:
                    self.callback_info("No network available")
                return

            lst = lastfm_manager.get_preference(TAG_LAST_PLAYED)
            if lst and lst.has_key(lastfm_manager.get_username().lower()):
                PlayNowModelFolder("Play now", self)

            SearchByArtistModelFolder("Search by artist", self)
            SearchByTagModelFolder("Search by tag", self)
            SearchByRadioModelFolder("Search by radio", self)
            FriendsModelFolder("Friends", self)
            NeighboursModelFolder("Neighbours", self)
            HistoryModelFolder("History", self)

            self.inform_loaded()

        self.is_loading = True
        ThreadedFunction(refresh_finished, refresh).start()


################################################################################
# Lastfm Options Model
################################################################################

class OptionsModel(ModelFolder):
    terra_type = "Model/Settings/Folder/InternetMedia/Lastfm"
    title = "Last.fm"

    def __init__(self, parent=None):
        ModelFolder.__init__(self, self.title, parent)

    def do_load(self):
        UserPassOptionsModel(self)
        ScrobblerOptionsModel(self)


MixedListItemDual = mger.get_class("Model/Settings/Folder/MixedList/Item/Dual")
class UserPassOptionsModel(MixedListItemDual):
    terra_type = "Model/Settings/Folder/InternetMedia/Lastfm/UserPass"
    title = "Login to Last.fm"

    def __init__(self, parent=None):
        MixedListItemDual.__init__(self, parent)
        self.username = lastfm_manager.get_username()
        self.password = lastfm_manager.get_password()

    def get_title(self):
        if not lastfm_manager.is_logged():
            return "Login to Last.fm"
        else:
            return "Logged as %s" % lastfm_manager.get_username()

    def get_left_button_text(self):
        if not lastfm_manager.is_logged():
            return "Log on"
        else:
            return "Log off"

    def get_right_button_text(self):
        return "Change user"

    def on_clicked(self):
        if not self.is_logged():
            self.callback_use(self)

    def on_left_button_clicked(self):
        if not self.is_logged():
            self.username = lastfm_manager.get_username()
            self.password = lastfm_manager.get_password()
            self.callback_use(self)
        else:
            self.logout()
            self.callback_update(self)
            self.callback_killall()

    def on_right_button_clicked(self):
        self.username = ""
        self.password = ""
        self.callback_use(self)

    def logout(self):
        lastfm_manager.logout()

    def is_logged(self):
        return lastfm_manager.is_logged()


MixedListItemOnOff = mger.get_class("Model/Settings/Folder/MixedList/Item/OnOff")
class ScrobblerOptionsModel(MixedListItemOnOff):
    terra_type = "Model/Settings/Folder/InternetMedia/Lastfm/Scrobbler"
    title = "Scrobble your music"

    def __init__(self, parent=None):
        MixedListItemOnOff.__init__(self, parent)

    def get_state(self):
        return (self.title, lastfm_manager.scrobble_enabled)

    def on_clicked(self):
        self.set_scrobbler(not lastfm_manager.scrobble_enabled)
        self.callback_update(self)

    def set_scrobbler(self, enable):
        lastfm_manager.scrobble_enabled = enable


class HistoryOptionsModel(OptionsModelFolder):
    terra_type = "Model/Options/Folder/History/Lastfm"
    title = "Options"

    def __init__(self, parent, screen_controller=None):
        OptionsModelFolder.__init__(self, parent, screen_controller)
        ClearHistoryOptionModel(self)


class ClearHistoryOptionModel(ActionModelFolder):
    terra_type = "Model/Options/Action/History/Lastfm/Clear"
    name = "Clear history"

    def execute(self):
        self.parent.screen_controller.clear_history()
        return True
