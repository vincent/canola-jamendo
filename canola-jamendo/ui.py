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

import logging

from terra.core.manager import Manager
from terra.ui.base import PluginThemeMixin

from model import AudioLocalModel, PromptModelFolder, HistoryModelFolder, \
    HistoryOptionsModel


manager = Manager()
CanolaError = manager.get_class("Model/Notify/Error")
YesNoDialogModel = manager.get_class("Model/YesNoDialog")
EntryDialogModel = manager.get_class("Model/EntryDialog")
BaseListController = manager.get_class("Controller/Folder")
BaseAudioPlayerController = manager.get_class("Controller/Media/Audio")
OptionsControllerMixin = manager.get_class("OptionsControllerMixin")

log = logging.getLogger("plugins.canola-jamendo.ui")


class ListController(BaseListController, OptionsControllerMixin):
    """Last.fm Navigation List.

    This is the basic list of Last.fm plugin. It shows all
    navigation possibilities. It extends the base Canola
    list to show a search dialog in some cases.

    @see: BaseListController
    """
    terra_type = "Controller/Folder/Task/Audio/Lastfm"

    def __init__(self, model, canvas, parent):
        BaseListController.__init__(self, model, canvas, parent)
        OptionsControllerMixin.__init__(self)
        self.model.callback_info = self.cb_info
        self.model.callback_notify = self.cb_notify

    def cb_info(self, msg):
        """Display a message in the screen."""
        self.view.part_text_set("message", msg)

    def cb_notify(self, err):
        """Display a message in a notify window."""
        self.parent.show_notify(err)

    def cb_on_clicked(self, view, index):
        model = self.model.children[index]

        if not isinstance(model, PromptModelFolder) or \
                not model.prompt_based:
            BaseListController.cb_on_clicked(self, view, index)
            return

        def do_search(ignored, text):
            if text is not None:
                model.query = text
                BaseListController.cb_on_clicked(self, view, index)

        dialog = EntryDialogModel(model.prompt_title, model.prompt_label,
                                  model.prompt_value, do_search)
        self.parent.show_notify(dialog)

    def delete(self):
        self.model.callback_info = None
        self.model.callback_notify = None
        OptionsControllerMixin.delete(self)
        BaseListController.delete(self)


class HistoryListController(ListController):
    terra_type = "Controller/Folder/Task/Audio/Lastfm/History"

    def options_model_get(self):
        return HistoryOptionsModel(None, self)

    def cb_on_clicked(self, view, index):
        # History doesn't depend on searching, so we just use original function
        BaseListController.cb_on_clicked(self, view, index)

    def clear_history(self):
        self.model.delete_model_all()
        self.model.reload()


class AudioPlayerController(PluginThemeMixin, BaseAudioPlayerController):
    terra_type = "Controller/Folder/Task/Audio/Lastfm/Service"
    plugin = "lastfm"

    connection_error_msg = "An error has occurred in your session.<br>" + \
        "The server may be down or you may be experiencing network problems."

    # disable unused properties from parent
    repeat = None
    shuffle = None
    MAX_FAILS_ALLOWED = 10

    def __init__(self, model, canvas, parent):
        self.parent_model = model
        self.init_ok = False
        self.end_reached = False
        self.transition_completed = False
        self.dummy_model = AudioLocalModel(model)

        BaseAudioPlayerController.__init__(self, self.dummy_model, canvas, parent)
        self.view.title = "Last.fm - now playing"

        self.parent_model.callback_notify = self._show_notify
        self.parent_model.callback_no_track_found = self.cb_no_track_found
        self.parent_model.callback_search_finished = self.cb_search_finished
        self.parent_model.load()

        self.view.set_tracking_state(enable=False)

        # disable repeat / shuffle
        self.repeat = None
        self.shuffle = None
        self.cb_repeat()
        self.cb_shuffle()

        self.unable_to_read_count = 0

        self.media_buttons = None
        self.disable_trackbar()
        self.previous_state(enabled=False)

    def create_media_buttons(self):
        self.media_buttons = self.PluginEdjeWidget("widget/media_buttons",
                                                   self.audio_screen)
        self.audio_screen.media_info.part_swallow("bottom_panel",
                                                  self.media_buttons)
        self.media_buttons.signal_callback_add("ban,clicked", "",
                                               self.cb_ban_clicked)
        self.media_buttons.signal_callback_add("love,clicked", "",
                                               self.cb_love_clicked)
        self.change_ban_state(False)
        self.change_love_state(False)

    def cb_no_track_found(self):
        self.end_reached = True
        self.next_state(enabled=False)
        # if not initialized ok show message
        if not self.init_ok:
            self.parent.show_notify(CanolaError("No content to play at this time"))
            self.block_controls()
        self.view.throbber_stop()

    def setup_interface(self):
        BaseAudioPlayerController.setup_interface(self)
        # enforce gstreamer-mp3 backend
        self.pl_iface.set_player("gstreamer-mp3")

    def theme_changed(self):
        BaseAudioPlayerController.theme_changed(self)
        if self.media_buttons is not None:
            self.audio_screen.media_info.part_swallow("bottom_panel",
                                                      self.media_buttons)
        self.view.set_tracking_state(enable=False)
        self.previous_state(enabled=False)

    def change_ban_state(self, full=True):
        if self.media_buttons is None:
            return

        self.ban_pressed = full
        if self.ban_pressed:
            self.media_buttons.signal_emit("ban,full", "")
        else:
            self.media_buttons.signal_emit("ban,empty", "")

    def change_love_state(self, full=True):
        if self.media_buttons is None:
            return

        self.love_pressed = full
        if self.love_pressed:
            self.media_buttons.signal_emit("love,full", "")
        else:
            self.media_buttons.signal_emit("love,empty", "")

    def cb_ban_clicked(self, obj, emission, source):
        if self.ban_pressed:
            return

        def cb_confirm(dialog, ok):
            if ok:
                self.model.ban_track()
                self.change_ban_state(True)
                self.next()

        self.parent.show_notify(YesNoDialogModel("Do you really want "
                                                 "to ban this track?", cb_confirm))

    def cb_love_clicked(self, obj, emission, source):
        if self.love_pressed:
            return

        self.model.love_track()
        self.change_love_state(True)

    def _show_notify(self, err):
         self.parent.show_notify(err)
         self.view.throbber_stop()
         self.block_controls()

    def cb_search_finished(self, *ignored):
        log.warning("lastfm playlist received len(%d)" % \
                        len(self.parent_model.children))

        self.initialize_list()

    def initialize_list(self, ok=False):
        if not self.parent_model.children:
            return

        if not ok and not self.transition_completed:
            return

        self.parent_model.update_history()

        log.debug("segment playlist: %s" % str(self.parent_model.children))

        if self.media_buttons is None:
            self.create_media_buttons()

        self.init_ok = True
        self.model.parent.current = 0
        self.model = self.parent_model.children[0]
        if self.transition_completed:
            self._change_model()
            self.update_model(self.model)
            self.current = self.model.parent.current
            self.setup_view()

    def _player_error(self, error_code):
        if error_code == self.ERROR_PLAYING:
            # could not read from resource
            # try to go to the next music
            self.unable_to_read_count += 1
            if self.unable_to_read_count < self.MAX_FAILS_ALLOWED:
                self.next()
            else:
                self._show_notify(CanolaError(self.connection_error_msg))
            log.error("unable to read from resource")
        elif error_code == self.ERROR_FILE_NOT_FOUND:
            # resource not found
            self._show_notify(CanolaError(self.connection_error_msg))
            log.error("resource not found")
        elif error_code == self.ERROR_PLAYER_GENERIC:
            # ignore internal flow error that follows the above errors
            log.error("gstreamer internal flow error")
            pass
        elif error_code == self.ERROR_UNKNOWN:
            self._show_notify(CanolaError(self.connection_error_msg))
        else:
            BaseAudioPlayerController._player_error(self, error_code)

    def _error_handler(self, error):
        BaseAudioPlayerController._error_handler(self, error)
        str_error = str(error)
        self._show_notify(CanolaError(str_error))

    def setup_model(self, view=True):
        if self.parent_model.children:
            BaseAudioPlayerController.setup_model(self, view)

    def refresh_remote_cover(self):
        def cb_downloaded(path):
            self.model.cover = path
            self.audio_screen._setup_cover()
            log.warning("trying to setup cover: %s" % path)

        self.model.request_cover(cb_downloaded)

    def play(self):
        BaseAudioPlayerController.play(self)
        self.set_volume(self.volume) # XXX: force volume

    def set_uri(self, uri):
        BaseAudioPlayerController.set_uri(self, uri, False)

    def _change_model(self):
        log.warning("changing model")
        self.change_ban_state(False)
        self.change_love_state(False)
        self.refresh_remote_cover()
        self.update_trackbar()
        self.model.uri = self.model.remote_uri
        self.setup_model(view=False)

    def transition_in_finished_cb(self, obj, emission, source):
        BaseAudioPlayerController.transition_in_finished_cb(self,
                                                        obj, emission, source)
        self.initialize_list(True)
        self.transition_completed = True

    def prev(self):
        pass # previous disabled

    def resume(self):
        if self.state != self.STATE_NONE:
            # if not in consistent state, jump to next song.
            # (lastfm does not permit to access a song twice).
            if self.state not in (self.STATE_PLAYING, self.STATE_PAUSED):
                self.next()
        BaseAudioPlayerController.resume(self)

    def next(self):
        if self.model.parent.current == len(self.model.parent.children) - 1:
            self.stop()
            self.view.throbber_start()
            self.parent_model.reload()
        else:
            BaseAudioPlayerController.next(self)

    def options_model_get(self):
        # there is no option
        return None

    def _player_eos(self, *ignored):
        log.warning("received EOS from player")
        self.next()

    def delete(self):
        if self.media_buttons is not None:
            self.media_buttons.delete()
        BaseAudioPlayerController.delete(self)
        self.parent_model.callback_notify = None
        self.parent_model.callback_search_finished = None
        self.model = None
        self.parent_model.unload()
