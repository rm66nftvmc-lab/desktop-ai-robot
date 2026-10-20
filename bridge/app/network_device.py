"""Optional device-only LAN WebSocket listener; never exposes web/API routes."""
import hmac
import ipaddress
import json
import threading
from http import HTTPStatus

from websockets.sync.server import serve
from websockets.protocol import State


class NetworkPort:
    def __init__(self, connection):
        self.connection = connection
        self.closed = threading.Event()
        self.buffer = bytearray()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.closed.set()
        self.connection.close()

    def write(self, value):
        try:
            self.connection.send(bytes(value))
        except Exception as exc:
            raise OSError('Device network write failed') from exc

    def read(self, count):
        if not self.buffer:
            try:
                value = self.connection.recv(timeout=0.005)
            except TimeoutError:
                return b''
            except Exception as exc:
                raise OSError('Device network disconnected') from exc
            if not isinstance(value, bytes):
                raise ValueError('Device requires binary frames')
            self.buffer.extend(value)
        value = bytes(self.buffer[:count])
        del self.buffer[:count]
        return value


class NetworkDevices:
    def __init__(self, directory):
        self.path = directory / 'device-network.json'
        self.lock = threading.Lock()
        self.pending = None
        self.active = None
        self.server = None
        self.error = None

    def start(self):
        if not self.path.is_file():
            return
        try:
            config = json.loads(self.path.read_text(encoding='utf-8'))
            host, port, token = config['host'], config['port'], config['token']
            address = ipaddress.ip_address(host)
            if address.version != 4 or not address.is_private or address.is_unspecified:
                raise ValueError('Device listener needs a private IPv4 address')
            if type(port) is not int or not 1024 <= port <= 65535 or len(token) < 32:
                raise ValueError('Invalid device listener configuration')

            def authenticate(connection, request):
                values = request.headers.get_all('Authorization')
                if (request.path != '/device' or len(values) != 1
                        or not hmac.compare_digest(values[0].encode(), ('Bearer ' + token).encode())
                        or request.headers.get_all('Origin')):
                    return connection.respond(HTTPStatus.UNAUTHORIZED, 'Device authentication required')

            self.server = serve(self._accept, host, port, process_request=authenticate,
                                max_size=4096, max_queue=16, compression=None,
                                open_timeout=5, close_timeout=1, ping_interval=10, ping_timeout=10)
            threading.Thread(target=self.server.serve_forever, daemon=True,
                             name='device-websocket-listener').start()
        except (OSError, ValueError, KeyError, TypeError):
            self.error = 'Wi-Fi device listener could not start; USB remains available'

    def _accept(self, connection):
        port = NetworkPort(connection)
        with self.lock:
            if self.pending or self.active:
                connection.close(1013, 'Device already connected')
                return
            self.pending = port
        while not port.closed.wait(0.1):
            if connection.state is State.CLOSED:
                port.close()
        with self.lock:
            if self.pending is port:
                self.pending = None
            if self.active is port:
                self.active = None

    def take(self):
        with self.lock:
            port, self.pending = self.pending, None
            if port:
                self.active = port
            return port

    def snapshot(self):
        return {'configured': self.path.is_file(), 'listening': self.server is not None,
                'last_error': self.error}

    def stop(self):
        with self.lock:
            ports = [self.pending, self.active]
        for port in ports:
            if port:
                port.close()
        if self.server:
            self.server.shutdown()
