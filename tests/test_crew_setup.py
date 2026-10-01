import os
import unittest
from unittest.mock import patch

import band_agent
import crew_setup


class CrewSetupEnvValidationTests(unittest.TestCase):
    def test_require_env_vars_raises_clear_message_when_missing(self):
        with self.assertRaisesRegex(
            ValueError,
            "FEATHERLESS_API_KEY|FEATHERLESS_BASE_URL|FEATHERLESS_MODEL",
        ):
            crew_setup.require_env_vars(
                {
                    "FEATHERLESS_API_KEY": "abc",
                    "FEATHERLESS_BASE_URL": "https://example.com",
                }
            )

    def test_build_llm_raises_clear_runtime_error_when_init_fails(self):
        with patch("crew_setup.LLM", side_effect=RuntimeError("bad model")):
            with self.assertRaisesRegex(
                RuntimeError,
                "FEATHERLESS_API_KEY|FEATHERLESS_BASE_URL|FEATHERLESS_MODEL|Featherless",
            ):
                crew_setup.build_llm(
                    {
                        "FEATHERLESS_API_KEY": "abc",
                        "FEATHERLESS_BASE_URL": "https://api.featherless.ai/v1",
                        "FEATHERLESS_MODEL": "featherless-ai/Qwen/Qwen2.5-72B-Instruct",
                    }
                )

    def test_build_llm_prefixes_provider_for_openai_compatible_model(self):
        with patch("crew_setup.LLM") as llm_cls:
            crew_setup.build_llm(
                {
                    "FEATHERLESS_API_KEY": "abc",
                    "FEATHERLESS_BASE_URL": "https://api.featherless.ai/v1",
                    "FEATHERLESS_MODEL": "featherless-ai/Qwen/Qwen2.5-72B-Instruct",
                }
            )

        llm_cls.assert_called_once_with(
            model="openai/featherless-ai/Qwen/Qwen2.5-72B-Instruct",
            base_url="https://api.featherless.ai/v1",
            api_key="abc",
        )

    def test_crew_setup_exports_module_level_agent_slots(self):
        self.assertTrue(hasattr(crew_setup, "planner"))
        self.assertTrue(hasattr(crew_setup, "implementer"))
        self.assertTrue(hasattr(crew_setup, "verifier"))

    def test_build_agents_returns_generic_roles(self):
        planner, implementer, verifier = crew_setup.build_agents("gpt-4o-mini")

        self.assertEqual(planner.role, "Planner")
        self.assertEqual(implementer.role, "Implementer")
        self.assertEqual(verifier.role, "Verifier")

    def test_band_adapter_receives_provider_and_featherless_environment(self):
        env = {
            "FEATHERLESS_API_KEY": "test-key",
            "FEATHERLESS_BASE_URL": "https://api.featherless.ai/v1",
            "FEATHERLESS_MODEL": "Qwen/Qwen2.5-72B-Instruct",
            "PLANNER_AGENT_ID": "planner-id",
            "PLANNER_API_KEY": "planner-key",
        }

        with patch.dict("os.environ", env):
            with patch("band_agent.ensure_agents", return_value=(None, None, None)):
                with patch("band_agent.CrewAIAdapter") as adapter_cls:
                    with patch("band_agent.Agent.create", return_value="agent"):
                        result = band_agent.build_band_agent("planner")

        self.assertEqual(result, "agent")
        self.assertEqual(
            adapter_cls.call_args.kwargs["model"],
            "openai/Qwen/Qwen2.5-72B-Instruct",
        )

    def test_implementer_uses_opencode(self):
        env = {
            "FEATHERLESS_API_KEY": "test-key",
            "FEATHERLESS_BASE_URL": "https://api.featherless.ai/v1",
            "FEATHERLESS_MODEL": "Qwen/Qwen2.5-72B-Instruct",
            "IMPLEMENTER_AGENT_ID": "implementer-id",
            "IMPLEMENTER_API_KEY": "implementer-key",
        }

        with patch.dict("os.environ", env):
            with patch("band_agent.OpencodeAdapter") as adapter_cls:
                with patch("band_agent.Agent.create", return_value="agent"):
                    result = band_agent.build_band_agent("implementer")

        self.assertEqual(result, "agent")
        adapter_cls.assert_called_once()

        config = adapter_cls.call_args.kwargs["config"]
        self.assertEqual(config.provider_id, "featherless")
        self.assertEqual(config.model_id, "MiniMaxAI/MiniMax-M2.5")
        self.assertEqual(config.approval_mode, "auto_accept")

    def test_verifier_uses_opencode(self):
        env = {
            "FEATHERLESS_API_KEY": "test-key",
            "FEATHERLESS_BASE_URL": "https://api.featherless.ai/v1",
            "FEATHERLESS_MODEL": "Qwen/Qwen2.5-72B-Instruct",
            "VERIFIER_AGENT_ID": "verifier-id",
            "VERIFIER_API_KEY": "verifier-key",
        }

        with patch.dict("os.environ", env):
            with patch("band_agent.OpencodeAdapter") as adapter_cls:
                with patch("band_agent.Agent.create", return_value="agent"):
                    result = band_agent.build_band_agent("verifier")

        self.assertEqual(result, "agent")
        adapter_cls.assert_called_once()

    def test_unknown_seat_is_rejected(self):
        with self.assertRaises(ValueError):
            band_agent.build_band_agent("unknown")


if __name__ == "__main__":
    unittest.main()
