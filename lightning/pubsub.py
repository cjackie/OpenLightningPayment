
from threading import Lock

class _PubsubCallback():
    def __init__(self, topic, callback):
        self.topic = topic
        self.callback = callback

class Pubsub():
    instance = None

    def __init__(self):
        '''
        Thread safe
        '''
        self._subscriber_id = 0
        self._callbacks = {}
        self._lock = Lock()
    
    def subscribe(self, topic: str, callback):
        '''
        @topic: str. only support exact match.
        @callback: func(topic: str, arg: any) -> None
        @return: id for unsubscribe
        '''
        self._lock.acquire()
        try:
            self._subscriber_id += 1
            self._callbacks[self._subscriber_id] = _PubsubCallback(topic, callback)
            return self._subscriber_id
        finally:
            self._lock.release()

    def unsubscribe(self, callback_id):
        assert callback_id in self._callbacks
        self._lock.acquire()
        try:
            del self._callbacks[callback_id]
        finally:
            self._lock.release()

    def publish(self, topic: str, payload):
        self._lock.acquire()
        try:
            callbacks = self._callbacks.values()
        finally:
            self._lock.release()

        for callback in callbacks:
            if callback.topic == topic:
                callback.callback(topic, payload)

Pubsub.instance = Pubsub()

        
