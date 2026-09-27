import unittest
from unittest.mock import patch

import crew_setup


class CrewSetupEnvValidationTests(unittest.TestCase):
    def test_require_env_vars_raises_clear_message_when_missing(self):
        with self.assertRaisesRegex(ValueError, "FEATHERLESS_API_KEY|FEATHERLESS_BASE_URL|FEATHERLESS_MODEL"):
            crew_setup.require_env_vars({
                "FEATHERLESS_API_KEY": "abc",
                "FEATHERLESS_BASE_URL": "https://example.com",
            })

    def test_build_llm_raises_clear_runtime_error_when_init_fails(self):
        with patch("crew_setup.LLM", side_effect=RuntimeError("bad model")):
            with self.assertRaisesRegex(RuntimeError, "FEATHERLESS_API_KEY|FEATHERLESS_BASE_URL|FEATHERLESS_MODEL|Featherless"):
                crew_setup.build_llm({
                    "FEATHERLESS_API_KEY": "abc",
                    "FEATHERLESS_BASE_URL": "https://api.featherless.ai/v1",
                    "FEATHERLESS_MODEL": "featherless-ai/Qwen/Qwen2.5-72B-Instruct",
                })


if __name__ == "__main__":
    unittest.main()
