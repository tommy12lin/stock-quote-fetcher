"""Stateless proxy authentication and domain-separated browser session tokens."""
import hashlib
import hmac
import os
import re
import time

WINDOW = 60
SESSION_TTL = 3600


class Auth:
    def __init__(self, current, previous=None, clock=time.time):
        if not current or len(current.encode()) < 32:
            raise ValueError('PROXY_HMAC_SECRET 必須設定且至少 32 bytes。')
        if previous and len(previous.encode()) < 32:
            raise ValueError('PROXY_HMAC_SECRET_PREV 至少需要 32 bytes。')
        self.keys = tuple(key.encode() for key in (current, previous) if key)
        self.clock = clock

    @classmethod
    def from_env(cls):
        return cls(os.environ.get('PROXY_HMAC_SECRET'), os.environ.get('PROXY_HMAC_SECRET_PREV'))

    def matches(self, message, signature):
        if not re.fullmatch(r'[0-9a-f]{64}', signature or ''):
            return False
        results = [hmac.compare_digest(hmac.new(key, message, hashlib.sha256).hexdigest(), signature)
                   for key in self.keys]
        return any(results)

    def timestamp_valid(self, timestamp):
        return bool(re.fullmatch(r'[0-9]{1,12}', timestamp or '')
                    and abs(self.clock() - int(timestamp)) <= WINDOW)

    def verify_request(self, timestamp, method, target, body, signature):
        if not self.timestamp_valid(timestamp):
            return False
        message = timestamp.encode() + b'|' + method.encode('ascii') + b'|' + target + b'|' + hashlib.sha256(body).hexdigest().encode()
        return self.matches(message, signature)

    def issue_session(self):
        issued = str(int(self.clock()))
        message = ('portfolio-session-v1|' + issued).encode()
        return issued + '.' + hmac.new(self.keys[0], message, hashlib.sha256).hexdigest()

    def verify_session(self, token):
        issued, separator, signature = (token or '').partition('.')
        if not separator or not re.fullmatch(r'[0-9]{1,12}', issued):
            return False
        age = self.clock() - int(issued)
        return -WINDOW <= age < SESSION_TTL and self.matches(('portfolio-session-v1|' + issued).encode(), signature)
