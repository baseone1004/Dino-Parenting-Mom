import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ConfigReloadTests(unittest.TestCase):
    def test_reload_mutates_shared_dict(self):
        from app import config
        original = config.cfg
        with patch("app.config.load", return_value={"accounts": [], "posting": {"mode": "live"}}):
            config.reload()
        self.assertIs(config.cfg, original)
        self.assertEqual(config.cfg["posting"]["mode"], "live")


class CardTests(unittest.TestCase):
    def test_local_renderer_produces_carousel(self):
        from app import local_cards
        with tempfile.TemporaryDirectory() as td, patch.object(local_cards, "CARDS_DIR", Path(td)):
            paths = local_cards.render_cards(123, "주방 정리 꿀팁", ["첫 번째 팁", "두 번째 팁"])
            self.assertEqual(len(paths), 3)
            self.assertTrue(all(p.exists() and p.stat().st_size > 1000 for p in paths))


class RetryTests(unittest.TestCase):
    def test_threads_retry_does_not_call_other_platforms(self):
        from app import service
        with patch.object(service, "publish_threads", return_value=True) as threads, \
             patch.object(service, "publish_facebook") as facebook, \
             patch.object(service, "publish_instagram") as instagram:
            self.assertTrue(service.retry_platform(7, "threads"))
        threads.assert_called_once_with(7)
        facebook.assert_not_called()
        instagram.assert_not_called()


class PublishClaimTests(unittest.TestCase):
    def test_claim_is_exclusive_until_release(self):
        from app import store
        store.init()
        post_id = store.add_post("claim-test", "topic", "body", None, store.DRAFT)
        try:
            self.assertTrue(store.claim_post(post_id))
            self.assertFalse(store.claim_post(post_id))
            store.release_post(post_id)
            self.assertTrue(store.claim_post(post_id))
        finally:
            store.release_post(post_id)
            store.delete_post(post_id)


if __name__ == "__main__":
    unittest.main()
