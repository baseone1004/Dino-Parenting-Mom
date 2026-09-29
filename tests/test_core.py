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
            paths = local_cards.render_cards(123, "주방 정리 꿀팁", ["첫 번째 팁", "두 번째 팁"],
                                             account_id="salimtem")
            self.assertEqual(len(paths), 3)
            self.assertTrue(all(p.exists() and p.stat().st_size > 1000 for p in paths))

    def test_product_photo_is_requested_for_every_card(self):
        from app import local_cards
        with tempfile.TemporaryDirectory() as td, patch.object(local_cards, "CARDS_DIR", Path(td)), \
             patch.object(local_cards.requests, "get", side_effect=RuntimeError("offline")), \
             patch.object(local_cards, "_background", wraps=local_cards._background) as background:
            local_cards.render_cards(124, "상품 사진 테스트", ["첫 번째", "두 번째"],
                                     "https://invalid.example/image.jpg", "kkultem")
        self.assertEqual(background.call_count, 3)
        self.assertTrue(all(call.args[0] == "https://invalid.example/image.jpg"
                            for call in background.call_args_list))


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


class DailyProductTests(unittest.TestCase):
    def test_daily_product_is_cached(self):
        from app import service
        item = {"displayName": "인기 수납함", "tacaItemId": 123}
        settings = {}
        with patch.object(service, "account_cfg", return_value={"auto_product": True, "link_source": "toss"}), \
             patch.dict(service.cfg, {"toss": {"use_api": True}}, clear=False), \
             patch.object(service.store, "get_setting", side_effect=lambda key: settings.get(key)), \
             patch.object(service.store, "set_setting", side_effect=lambda key, value: settings.__setitem__(key, value)), \
             patch.object(service.store, "log"), \
             patch.object(service.toss, "pick_trending_product", return_value=item) as pick, \
             patch.object(service.toss, "link_for_item", return_value="https://example.test/item"):
            first = service.select_daily_product("kkultem")
            second = service.select_daily_product("kkultem")
        self.assertEqual(first, second)
        self.assertEqual(first["product"], "인기 수납함")
        pick.assert_called_once()


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
