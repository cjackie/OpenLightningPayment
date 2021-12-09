from lightning.pubsub import Pubsub
import unittest

class TestPubsub(unittest.TestCase):

    def test_publishAndSubscribe(self):
        subscriber_data = [None, None]
        def subscriber(topic, payload):
            subscriber_data[0] = topic
            subscriber_data[1] = payload

        pubsub = Pubsub()
        topic = "topic-b"
        sub_id = pubsub.subscribe(topic, subscriber)
        pubsub.publish(topic, "hello sub")

        self.assertEqual(subscriber_data[0], topic)
        self.assertEqual(subscriber_data[1], "hello sub")

        sub_id = pubsub.unsubscribe(sub_id)
        pubsub.publish(topic, "hello sub2")
        self.assertEqual(subscriber_data[1], "hello sub")
