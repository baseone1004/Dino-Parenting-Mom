import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import ai_backend, service


class OpenAIBackendTests(unittest.TestCase):
    def test_responses_extracts_text_after_reasoning_and_keeps_prompts(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "status": "completed",
            "output": [
                {"type": "reasoning", "summary": []},
                {"type": "message", "content": [
                    {"type": "output_text", "text": " 한국어 게시문 "},
                ]},
            ],
        }
        with patch.object(ai_backend, "env", return_value="sk-test-only"), \
             patch.object(ai_backend.requests, "post", return_value=response) as post:
            result = ai_backend.OpenAIAPI().generate("말투 규칙", "글감")
        self.assertEqual(result, "한국어 게시문")
        self.assertEqual(post.call_args.kwargs["json"]["instructions"], "말투 규칙")
        self.assertEqual(post.call_args.kwargs["json"]["input"], "글감")
        self.assertFalse(post.call_args.kwargs["json"]["store"])

    def test_errors_do_not_expose_key_from_api_response(self):
        response = Mock(status_code=401, text="Invalid API key: sk-sensitive")
        with patch.object(ai_backend, "env", return_value="sk-sensitive"), \
             patch.object(ai_backend.requests, "post", return_value=response):
            with self.assertRaises(ai_backend.AIError) as error:
                ai_backend.OpenAIAPI().generate("system", "user")
        self.assertNotIn("sk-sensitive", str(error.exception))
        self.assertIn("401", str(error.exception))

    def test_incomplete_response_is_not_used_as_a_post(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "status": "incomplete", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": "truncated body"},
            ]}],
        }
        with patch.object(ai_backend, "env", return_value="sk-test-only"), \
             patch.object(ai_backend.requests, "post", return_value=response):
            with self.assertRaises(ai_backend.AIError):
                ai_backend.OpenAIAPI().generate("system", "user")

    def test_selected_openai_backend_does_not_call_claude(self):
        with patch.dict(ai_backend.cfg, {"ai": {"backend": "openai", "model": "gpt-5-mini"}}), \
             patch.object(ai_backend, "env", return_value="sk-test-only"), \
             patch.object(ai_backend, "HeadlessClaude") as claude:
            self.assertIsInstance(ai_backend.get_backend(), ai_backend.OpenAIAPI)
        claude.assert_not_called()


class CarouselWithOpenAIKeyTests(unittest.TestCase):
    def test_text_api_key_does_not_switch_to_single_image_renderer(self):
        post = {"id": 88, "account_id": "kkultem", "topic": "생활용품", "body": "본문"}
        paths = [Path(f"{i}.png") for i in range(1, 6)]
        with patch.dict(service.cfg, {"instagram": {"image_backend": "local"}}), \
             patch.object(service, "env", return_value="sk-test-only"), \
             patch.object(service, "public_base_url", return_value="https://example.test"), \
             patch.object(service, "build_card_slides", return_value=["팁"] * 4), \
             patch.object(service, "ensure_formal_body", return_value="본문입니다"), \
             patch.object(service, "cover_image_for", return_value=None), \
             patch.object(service, "render_cards_openai") as image_api, \
             patch("app.local_cards.render_cards", return_value=paths), \
             patch.object(service.store, "update_post"):
            urls = service.ensure_card_images(post)
        self.assertEqual(len(urls), 5)
        image_api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
