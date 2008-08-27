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
import logging
import xmlrpclib
from md5 import md5
from datetime import datetime
from time import mktime, localtime
from urllib import urlencode
from urllib2 import urlopen, Request
from terra.utils.encoding import to_utf8

try:
    from xml.etree import cElementTree as ElementTree
except ImportError:
    try:
        import cElementTree as ElementTree
    except ImportError:
 	from elementtree import ElementTree


log = logging.getLogger("plugins.canola-jamendo.client")


class TuningError(Exception):
    pass

class HandshakeError(Exception):
    pass

class AuthenticationError(Exception):
    pass

class JamendoException(Exception):
    pass


class Client(object):
    client_name = "tst"
    client_version = "0.1"
    protocol_version = '1.2'
    url_post_handshake = "http://post.audioscrobbler.com/"
    url_radio_handshake = "http://ws.audioscrobbler.com/radio/handshake.php"
    url_userfeed = "http://ws.audioscrobbler.com/1.0/user"
    url_xmlrpc = "http://ws.audioscrobbler.com/1.0/rw/xmlrpc.php"
    url_radio_xspf = "http://ws.audioscrobbler.com/radio/xspf.php"
    url_radio_adjust = "http://ws.audioscrobbler.com/radio/adjust.php"

    def __init__(self, username=None, password=None):
        self._logged = False
        self.now_url = None
        self.post_url = None
        self.session_id = None
        self.post_session_id = None
        self.username = username
        self.password = password
        self.base_url = None
        self.base_path = None
        self.stream_url = None
        self.user_url = None
        self.station_name = None
        self.discovery = 0
        self.proxy = xmlrpclib.ServerProxy(self.url_xmlrpc)

    def _get_logged(self):
        return self._logged

    logged = property(_get_logged)

    def _request(self, _url, **params):
        """Return url content in text.

        @parm url: url address.
        @parm params: dict of url parameters.
        """
        if params:
            _url = _url + "?" + urlencode(params)

        log.debug("requesting url: %s" % str(_url))
        return urlopen(_url).read()

    def _request_lines(self, _url, **params):
        """Return url content in text lines.

        @parm url: url address.
        @parm params: dict of url parameters.
        """
        if params:
            _url = _url + "?" + urlencode(params)

        log.debug("requesting url: %s" % str(_url))
        lines = urlopen(_url).readlines()
        return [c.strip() for c in lines]

    def check_login(func):
        """Used as decorator to validate login."""
        def new_def(*args, **kwds):
            self = args[0]
            if not self.logged:
                self.login()
            return func(*args, **kwds)
        return new_def

    def get_token_timestamp(self):
        """Return actual (token, timestamp)."""
        passwordmd5 = md5(self.password).hexdigest()
        timestamp = int(time.mktime(time.localtime()))
        token  = md5("%s%d" % (passwordmd5, timestamp)).hexdigest()
        return (token, timestamp)

    def get_friends(self, username):
        """Retrieve friends of a Jamendo user.

        @parm username: Jamendo username
        """
        url = "%s/%s/friends.xml" % (self.url_userfeed, username)
        xml = self._request(url)

        lst = []
        tree = ElementTree.fromstring(xml)
        for child in tree.getchildren():
            friend = Friend(to_utf8(child.get("username")))
            friend.url = child.find("url").text
            friend.image = child.find("image").text
            lst.append(friend)

        return lst

    def get_neighbours(self, username):
        """Retrieve neighbours of a last.fm user.

        @parm username: last.fm username
        """
        url = "%s/%s/neighbours.xml" % (self.url_userfeed, username)
        xml = self._request(url)

        lst = []
        tree = ElementTree.fromstring(xml)
        for child in tree.getchildren():
            neighbour = Neighbour(to_utf8(child.get("username")))
            neighbour.url = child.find("url").text
            neighbour.image = child.find("image").text
            lst.append(neighbour)

        return lst

    def _execute_rpc_method(self, method, *args):
        """Execute xml rpc method from last.fm server.

        @parm method: proxy method.
        @parm args: method arguments.
        """
        token, timestamp = self.get_token_timestamp()
        return method(self.username, str(timestamp), token, *args)

    def ban_track(self, artist_name, track_title):
        """Ban a last.fm track.

        @parm artist_name: artist name.
        @parm track_title: track title.
        @return: True if success and False otherwise.
        """
        r = self._execute_rpc_method(self.proxy.banTrack,
                                     artist_name, track_title)
        return (r == "OK")

    def love_track(self, artist_name, track_title):
        """Set a last.fm track as loved.

        @parm artist_name: artist name.
        @parm track_title: track title.
        @return: True if success and False otherwise.
        """
        r = self._execute_rpc_method(self.proxy.loveTrack,
                                     artist_name, track_title)
        return (r == "OK")

    def _check_userpass(func):
        """Used as decorator to check username and password."""
        def new_def(*args, **kwds):
            self = args[0]
            if not self.username:
                raise ValueError("Username cannot be empty.")
            if not self.password:
                raise ValueError("Password cannot be empty.")

            return func(*args, **kwds)

        return new_def

    def login(self):
        """Complete login to last.fm.
        Do first and second handshake."""
        try:
            self.handshake()
            self._logged = True
        except:
            self._logged = False
            raise

    def logout(self):
        """Logout from last.fm."""
        self._logged = False

    @_check_userpass
    def handshake(self):
        """First last.fm handshake."""
        ret = self._request_lines(self.url_radio_handshake,
                                  platform="linux",
                                  version=self.client_version,
                                  username=self.username,
                                  passwordmd5=md5(self.password).hexdigest())

        params = self.make_dict(ret)
        if params['session'] == 'FAILED':
            raise HandshakeError(params['msg'])
        else:
            self.session_id = params['session']
            self.stream_url = params['stream_url']
            self.base_url = params['base_url']
            self.base_path = params['base_path']

    @_check_userpass
    def second_handshake(self):
        """Second last.fm handshake. Necessary if you want
        to get xspf tracks."""
        token, timestamp = self.get_token_timestamp()

        ret = self._request_lines(self.url_post_handshake,
                                  hs="true", a=token, t=timestamp,
                                  u=self.username, p=self.protocol_version,
                                  c=self.client_name, v=self.client_version)

        if "OK" in ret:
            self.post_session_id = ret[1]
            self.now_url = ret[2]
            self.post_url = ret[3]
        else:
            self.post_session_id = None
            self._check_response(ret)

    def _check_response(self, response):
        """Check error responses to raise Exception."""
        if "BADAUTH" in response:
            raise AuthenticationError("Invalid username or password")
        elif "BANNED" in response:
            raise AuthenticationError("You have been banned from this server")
        elif "BADTIME" in response:
            pass # ignore bad time error (will not use audioscrobbler)
        elif "FAILED" in response:
            raise AuthenticationError("Authentication failed. Reason: " + response[0])
        elif "BADSESSION" in response:
            self._logged = False
            raise AuthenticationError("Bad session error")

    @check_login
    def tune(self, lastfm_url):
        """Tune the stream_url to play the specified last.fm url.

        List of lastfm urls:
            lastfm://user/$username/personal
            lastfm://user/$username/playlist
            lastfm://artist/$artistname
            lastfm://artist/$artistname/similarartists
            lastfm://globaltags/$tag
            lastfm://group/$groupname
            lastfm://user/$username/neighbours
            lastfm://user/$username/recommended/100
            lastfm://play/tracks/$trackid,$trackid,$trackid
        """
        lines = self._request_lines(self.url_radio_adjust,
                                    url=lastfm_url, lang="en",
                                    debug=0, session=self.session_id)

        params = self.make_dict(lines)
        response = params.get('response', None)

        if response == 'OK':
            self.user_url = params['url']
            self.station_name = params['stationname']
            self.discovery = params.get('discovery', 0)
        elif response:
            raise TuningError(response)
        else:
            raise TuningError("Unknown error")

    def tune_user(self, user, feature):
        """Tune stream_url to play last.fm user url."""
        self.tune("lastfm://user/%s/%s" % (user, feature))

    def make_dict(self, lines):
        result = {}
        for line in lines:
            key, val = line.split("=", True)
            result[key] = val.strip()
        return result

    @check_login
    def get_xspf_tracks(self):
        """Retrieve xspf tracks from last.fm."""
        xml = self._request(self.url_radio_xspf,
                            sk=self.session_id,
                            desktop=0.1, discovery=0)

        lst = []
        tree = ElementTree.fromstring(xml)
        tracklist = tree.find("trackList")
        for child in tracklist.findall("track"):
            track = Track(to_utf8(child.find("title").text),
                          child.find("id").text)

            track.album = Album(to_utf8(child.find("album").text or ""))
            track.artist = Artist(to_utf8(child.find("creator").text or ""))

            track.url = child.find("location").text
            track.duration = int(child.find("duration").text)
            track.image = child.find("image").text

            lst.append(track)

        return lst

    @check_login
    def now_playing(self, track, artist, album="", trackno="", length=""):
        if length and not isinstance(length, int):
            raise TypeError("Length must be int")

        if trackno and not isinstance(trackno, int):
            raise TypeError("Trackno must be int")

        query = {}
        query['s'] = self.post_session_id
        query['t'] = track
        query['a'] = artist
        query['b'] = album
        query['l'] = length
        query['n'] = trackno
        query['m'] = ""

        # need to use 'POST'
        req = Request(self.now_url, urlencode(query))
        self._check_response(self._request_lines(req))

    @check_login
    def submit(self, track, artist, album="", trackno="", length="",
               time = "", source="P"):

        if source in ("p", "P"):
            if not length:
                raise LastfmException("You must specify length")
        else:
            raise LastfmException("Source type not supported")

        if not isinstance(time, int):
            raise TypeError("Time must be int")

        query = {}
        query['s'] = self.post_session_id
        query['t[0]'] = track
        query['a[0]'] = artist
        query['b[0]'] = album
        query['l[0]'] = length
        query['n[0]'] = trackno
        query['i[0]'] = time
        query['o[0]'] = source
        query['r[0]'] = ""
        query['m[0]'] = ""

        # need to use 'POST'
        req = Request(self.post_url, urlencode(query))
        self._check_response(self._request_lines(req))


##############################################################################
# Client data
##############################################################################

class Friend(object):
    def __init__(self, username, url=None, image=None):
        self.username = username
        self.url = url
        self.image = image

    def __repr__(self):
        return "(username: %s, url: %s, image: %s)" % \
            (self.username, self.url, self.image)


class Neighbour(Friend):
    pass


class Artist(object):
    def __init__(self, name, mbid=None):
        self.mbid = mbid
        self.name = name
        self.rank = 0
        self.playcount = 0
        self.url = None
        self.image = None
        self.thumbnail = None

    def __repr__(self):
        return "(mbid: %s, name: %s, url: %s, rank: %d, playcount: %d, " \
            "image: %s, thumbnail: %s)" % \
            (self.mbid, self.name, self.url, self.rank, self.playcount,
             self.image, self.thumbnail)


class Track(object):
    def __init__(self, name, mbid=None):
        self.mbid = mbid
        self.name = name
        self.url = None
        self.rank = 0
        self.album = None
        self.artist = None
        self.playcount = 0
        self.uts_time = 0
        self.image = None
        self.streamable = False

    def __repr__(self):
        return "(mbid: %s, name: %s, artist: %s, url: %s, rank: %d, " \
            "playcount: %d, album: %s, date: %s, image: %s, streamable: %s)" % \
            (self.mbid, self.name, self.artist, self.url, self.rank,
             self.playcount, self.album, localtime(self.uts_time),
             self.image, self.streamable)


class Album(object):
    def __init__(self, name, mbid=None):
        self.mbid = mbid
        self.name = name
        self.url = None
        self.rank = 0
        self.artist = None
        self.playcount = 0
        self.image_small = None
        self.image_large = None
        self.image_medium = None

    def __repr__(self):
        return "(mbid: %s, name: %s, artist: %s, url: %s, rank: %d, " \
            "playcount: %d, image_small: %s, image_large: %s, image_medium: %s)" % \
            (self.mbid, self.name, self.artist, self.url, self.rank, self.playcount,
             self.image_small, self.image_large, self.image_medium)


if __name__ == "__main__":
    client = Client("user", "xxx")
