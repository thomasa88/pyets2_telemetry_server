#
# Copyright 2019 Thomas Axelsson <thomasa88@gmail.com>
#
# This file is part of pyets2_telemetry_server.
#
# pyets2_telemetry_server is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# pyets2_telemetry_server is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty
# of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyets2_telemetry_server.
# If not, see <https://www.gnu.org/licenses/>.
#

# SignalR protocol info:
# https://blog.3d-logic.com/2015/03/29/signalr-on-the-wire-an-informal-description-of-the-signalr-protocol/
# http://www.mithril.com.au/SignalR%20Protocol.docx (old protocol version)

import http
import http.server
import json
import os
import posixpath
import socket
import socketserver
import threading
import urllib

import pyets2lib.scshelpers

MODULE_DIR = os.path.dirname(os.path.realpath(__file__))
HTML_DIR = 'Html'

config_json = None

negotiate_base = {
    'Url': '/signalr',
    'ConnectionToken': '',
    'ConnectionId': '',
    'KeepAliveTimeout': 6.0,
    'DisconnectTimeout': 9.0,
    'ConnectionTimeout': 12.0,
    'TryWebSockets': False,
    'ProtocolVersion':'1.5',
    'TransportConnectTimeout': 5.0,
    'LongPollDelay': 0.0
}

connect_json = json.dumps({
        'C': 's-0,2CDDE7A|1,23ADE88|2,297B01B|3,3997404|4,33239B5',
        'S': 1,
        'M': []
    })

# Correct?
reconnect_json = json.dumps({})

start_json = json.dumps({ 'Response': 'started' })

poll_keepalive_json = json.dumps({})

pong_json = json.dumps({ 'Response': 'pong' })



class SignalrHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, logger, shared_data, stop_event,
                 request, client_address, server):
        self.logger_ = logger
        self.shared_data_ = shared_data
        self.stop_event_ = stop_event
        super().__init__(request, client_address, server)
        self.protocol_version = 'HTTP/1.1'

    # SimpleHTTPRequestHandler log function
    def log_message(self, format, *args):
        self.logger_.debug(format, *args)

    def translate_path(self, path):
        if not path.startswith('/signalr'):
            path = '/' + HTML_DIR + path
        else:
            path = '/' + path
        return self.simplehttprequesthandler_translate_path(path)

    # Python 3.6 SimpleHTTPRequestHandler does not have a "directory" option
    # so we must rewrite the function
    def simplehttprequesthandler_translate_path(self, path):
        """Translate a /-separated PATH to the local filename syntax.
        Components that mean special things to the local file system
        (e.g. drive or directory names) are ignored.  (XXX They should
        probably be diagnosed.)
        """
        # abandon query parameters
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        # Don't forget explicit trailing slash when normalizing. Issue17324
        trailing_slash = path.rstrip().endswith('/')
        try:
            path = urllib.parse.unquote(path, errors='surrogatepass')
        except UnicodeDecodeError:
            path = urllib.parse.unquote(path)
        path = posixpath.normpath(path)
        words = path.split('/')
        words = filter(None, words)
        path = MODULE_DIR
        for word in words:
            if os.path.dirname(word) or word in (os.curdir, os.pardir):
                # Ignore components that are not a simple file/directory name
                continue
            path = os.path.join(path, word)
        if trailing_slash:
            path += '/'
        return path

    def handle_one_request(self):
        if not self.stop_event_.is_set():
            super().handle_one_request()
        else:
            self.close_connection = True
            
    def do_GET(self):
        if not self.do_signalr():
            super().do_GET()

    def do_POST(self):
        self.do_signalr()
        # SimpleHTTPRequestHandler has no POST handling

    def do_signalr(self):
        try:
            return self.do_signalr_comm()
        except BrokenPipeError:
            # Client closed connection. Most likely left the web page.
            return True
        except Exception as e:
            # Each request is handled in a new thread, so we need to set up
            # exception logging
            scshelpers.log_exception(e)
            raise

    def do_signalr_comm(self):
        processed = True
        if self.path.startswith('/config.json'):
            self.read_data()
            self.write_response(config_json)
        elif self.path.startswith('/signalr/hubs'):
            # This response is too complex. Handing over to the file server.
            processed = False
        elif self.path.startswith('/signalr/negotiate'):
            self.read_data()
            token = self.server.add_client()
            negotiate = negotiate_base.copy()
            negotiate['ConnectionToken'] = token
            self.write_response(json.dumps(negotiate))
        elif self.path.startswith('/signalr/start'):
            self.read_data()
            self.write_response(start_json)
        elif self.path.startswith('/signalr/connect'):
            if 'transport=longPolling' in self.path:
                self.write_response(connect_json)
            else:
                # TODO: Correct response code?
                self.write_response('', code=http.HTTPStatus.BAD_REQUEST)
        elif self.path.startswith('/signalr/reconnect'):
            self.read_data()
            query = self.parse_query()
            token = query['connectionToken'][0]
            self.server.test_and_set_client_new(token, True)
            self.write_response(reconnect_json)
        elif self.path.startswith('/signalr/ping'):
            self.read_data()
            self.write_response(pong_json)
        elif self.path.startswith('/signalr/abort'):
            self.read_data()
            query = self.parse_query()
            token = query['connectionToken'][0]
            self.server.remove_client(token)
            self.write_response('')
        elif self.path.startswith('/signalr/poll'):
            data = self.read_data()
            post_data = urllib.parse.parse_qs(data)
            messageId = post_data['messageId'][0]

            query = self.parse_query()
            token = query['connectionToken'][0]
            new_client = self.server.test_and_set_client_new(token, False)
            
            telemetry_data = None
            shared_data = self.shared_data_
            with shared_data['condition']:
                # Wait for new data
                # wait() can release early, but we don't know how much
                # time that has passed, so we continue, to avoid waiting
                # too long before sending a keep-alive to the client.
                if (not shared_data['new_data'] and
                    not self.stop_event_.is_set() and
                    not new_client):
                    shared_data['condition'].wait(10.0)
                if shared_data['new_data'] or new_client:
                    shared_data['new_data'] = False
                    # Copy the data
                    telemetry_data = json.dumps(shared_data['telemetry_data'])

            if telemetry_data:
                poll_json = json.dumps(
                    {
                        'C': messageId,
                        'M': [
                            { 'H': 'ets2telemetryhub',
                              'M': 'UpdateData',
                              'A': [telemetry_data] }
                        ]
                    }
                )
            else:
                poll_json = poll_keepalive_json

            self.write_response(poll_json)
        elif self.path.startswith('/signalr/send'):
            data = self.read_data()
            post_data = urllib.parse.parse_qs(data)
            json_req = post_data['data'][0]
            req = json.loads(json_req)
            method = req['M']
            args = req['A']
            id = req['I']

            # TODO: if method == RequestData

            shared_data = self.shared_data_
            with shared_data['condition']:
                shared_data['new_data'] = False
                # Copy the data
                resp = { 'I': id,
                         'R': shared_data['telemetry_data'] }
                resp_json = json.dumps(resp)
            self.write_response(resp_json)
        else:
            processed = False
            
        return processed

        
    def read_data(self):
        length = self.headers['Content-Length']
        if length is None:
            return bytes()
        else:
            utf8_data = self.rfile.read(int(length))
            return utf8_data.decode('utf-8')

    def parse_query(self):
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        
    def write_response(self, data, code=http.HTTPStatus.OK):
        utf8_data = data.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-type', 'application/json; charset=UTF-8')
        self.send_header('Connection', 'keep-alive')
        self.send_header('Content-Length', len(utf8_data))
        # TODO: Transfer-Encoding: chunked. Will likely affect shutdown behavior.
        self.end_headers()
        self.wfile.write(utf8_data)

# Python 3.7 has built-in ThreadingHTTPServer, but Python 3.6 does not
class SignalrHttpServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    PORT_NUMBER = 25555
    allow_reuse_address = True
    # deamon_threads leads to crashes in the C++ process..
    # Doing manual handling with Events, for now.
    # daemon_threads = True

    def __init__(self, logger, shared_data):
        self.logger_ = logger
        self.stop_event_ = threading.Event()
        self.shared_data_ = shared_data
        self.collect_skins()

        # State
        self._state_lock = threading.RLock()
        self._token_counter = 0
        self._clients = {}

        # Make sure code does not get stuck in blocking read when trying to exit
        socket.setdefaulttimeout(1)
        
        def handler(*args):
            return SignalrHandler(logger, shared_data, self.stop_event_, *args)
        super().__init__(('', SignalrHttpServer.PORT_NUMBER), handler)

    def collect_skins(self):
        global config_json
        skin_configs = []
        skins_dir = os.path.join(MODULE_DIR, HTML_DIR, 'skins')
        for d in os.scandir(skins_dir):
            if not d.is_dir():
                continue
            with open(d.path + '/config.json') as config_file:
                try:
                    skin = json.load(config_file)
                except:
                    self.logger_.warning("Failed to parse %s" % filename)
                    continue
                # Make sure name has the correct casing
                skin_config = skin['config']
                skin_config['name'] = d.name
                skin_configs.append(skin_config)
        config_json = json.dumps( { 'skins': skin_configs } )

    def add_client(self, token=None):
        with self._state_lock:
            # TODO: Handle client timeout and abort -> clean-up
            if token is None:
                self._token_counter += 1
                token = str(self._token_counter)
            else:
                # Server probably restarted with old clients. Try to compensate.
                self._token_counter = int(token) + 10
            state = ClientState()
            state.token = token
            state.new = True
            self._clients[token] = state
            return state.token
    
    def _get_client(self, token):
        client = self._clients.get(token)
        if client is None:
            self.add_client(token)
            client = self._clients.get(token)
        return client

    def remove_client(self, token):
        with self._state_lock:
            if token in self._clients:
                del self._clients[token]

    def test_and_set_client_new(self, token, new_value):
        with self._state_lock:
            client = self._get_client(token)
            old_value = client.new
            client.new = new_value
            return old_value
        
    def shutdown(self):
        # Stop accepting new connections
        super().shutdown()

        # Make sure existing connections tear down
        self.stop_event_.set()
        # Cancel the polling, to avoid blocking
        with self.shared_data_['condition']:
            self.shared_data_['condition'].notify_all()

class ClientState:
    pass
