"""In-memory authorization attached to queued model requests, never persisted."""
import threading


class MessageAccess:
    def __init__(self, sessions):
        self.sessions = sessions
        self._lock = threading.Lock()
        self._tickets = {}

    def browser(self, message_id, session):
        with self._lock:
            self._tickets[message_id] = ('browser', session)

    def voice(self, message_id, grant):
        with self._lock:
            self._tickets[message_id] = ('voice', grant)

    def allowed(self, message_id):
        with self._lock:
            ticket = self._tickets.get(message_id)
        if not ticket or not ticket[1]:
            return False
        if ticket[0] == 'browser':
            return self.sessions.valid(ticket[1])
        return self.sessions.voice_grant() == ticket[1]

    def release(self, message_id):
        with self._lock:
            self._tickets.pop(message_id, None)

    def revoked(self):
        with self._lock:
            ids = list(self._tickets)
        return [message_id for message_id in ids if not self.allowed(message_id)]
