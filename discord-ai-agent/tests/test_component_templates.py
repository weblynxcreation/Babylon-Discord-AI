from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from component_templates import (  # noqa: E402
    ComponentTemplateError,
    SLASH_COMMAND_TEMPLATE_NAMES,
    load_template_payload,
    render_template_payload,
    template_placeholders,
)


class ComponentTemplateTests(unittest.TestCase):
    def test_item_template_uses_a_section_thumbnail(self):
        payload = load_template_payload("item")
        container = payload["components"][0]
        header = container["components"][0]

        self.assertEqual(payload["flags"], 32768)
        self.assertEqual(container["type"], 17)
        self.assertEqual(header["type"], 9)
        self.assertEqual(header["accessory"]["type"], 11)
        self.assertEqual(
            header["accessory"]["media"]["url"],
            "{{item_image_url}}",
        )
        self.assertIn("]({{item_wiki_url}})", header["components"][0]["content"])
        self.assertIn(
            "[Capital Rift Wiki]({{item_wiki_url}})",
            container["components"][-2]["content"],
        )

    def test_agentic_investment_analysis_links_data_and_uses_discord_time(self):
        values = {
            name: name.replace("_", " ")
            for name in template_placeholders("agentic_investment_analysis")
        }
        values.update(
            accent_color=5763719,
            item_wiki_url="https://wiki.capitalrift.com/items/standard_window/",
            item_image_url="https://wiki.capitalrift.com/icons/standard_window.png",
            timestamp_unix="1767657600",
        )

        payload = render_template_payload("agentic_investment_analysis", values)
        serialized = str(payload)

        self.assertEqual(payload["components"][0]["accent_color"], 5763719)
        self.assertIn(
            "comparison_visual",
            str(load_template_payload("agentic_investment_analysis")),
        )
        self.assertEqual(
            payload["components"][0]["components"][0]["accessory"]["media"]["url"],
            "https://wiki.capitalrift.com/icons/standard_window.png",
        )
        self.assertIn("<t:1767657600:f>", serialized)
        self.assertIn("<t:1767657600:R>", serialized)

    def test_babylon_holdings_how_to_uses_a_logo_thumbnail(self):
        payload = render_template_payload(
            "info_babylon_holdings_how_to",
            {
                "trust_logo_url": "attachment://babylon-trust.png",
                "timestamp_unix": "1767657600",
                "data_quality": "-# ✓ Preview source verified.",
            },
        )
        header = payload["components"][0]["components"][0]

        self.assertEqual(header["accessory"]["type"], 11)
        self.assertEqual(
            header["accessory"]["media"]["url"],
            "attachment://babylon-trust.png",
        )

    def test_share_trade_guide_uses_a_logo_thumbnail(self):
        payload = render_template_payload(
            "info_share_trading_how_to",
            {
                "trust_logo_url": "attachment://babylon-trust-primary-logo.png",
                "timestamp_unix": "1767657600",
                "data_quality": "-# ✓ Preview source verified.",
            },
        )

        self.assertEqual(
            payload["components"][0]["components"][0]["accessory"]["media"]["url"],
            "attachment://babylon-trust-primary-logo.png",
        )

    def test_slash_command_templates_render_timestamps(self):
        for name in (
            "slash_command_confirmation",
            "slash_command_settings",
            "slash_command_error",
        ):
            with self.subTest(template=name):
                values = {
                    key: key.replace("_", " ")
                    for key in template_placeholders(name)
                }
                values["timestamp_unix"] = "1767657600"
                payload = render_template_payload(name, values)
                self.assertIn("<t:1767657600:f>", str(payload))

    def test_every_command_specific_template_renders(self):
        for name in SLASH_COMMAND_TEMPLATE_NAMES:
            with self.subTest(template=name):
                values = {
                    key: key.replace("_", " ")
                    for key in template_placeholders(name)
                }
                values["timestamp_unix"] = "1767657600"
                payload = render_template_payload(name, values)
                self.assertEqual(payload["flags"], 32768)

    def test_production_layout_does_not_require_a_transport_entity(self):
        placeholders = template_placeholders("production_line")

        self.assertIn("layout_sketch", placeholders)
        self.assertNotIn("transport_system", placeholders)

    def test_production_layout_rejects_lines_that_are_too_wide(self):
        values = {
            key: key.replace("_", " ")
            for key in template_placeholders("production_line")
        }
        values["layout_sketch"] = "x" * 45

        with self.assertRaises(ComponentTemplateError) as context:
            render_template_payload("production_line", values)

        self.assertIn("44 characters", str(context.exception))

    def test_render_replaces_values_recursively(self):
        values = {
            name: name.replace("_", " ")
            for name in template_placeholders("item")
        }
        values["item_image_url"] = (
            "https://wiki.capitalrift.com/icons/clothing_rack.png"
        )

        payload = render_template_payload("item", values)
        serialized = str(payload)
        image_url = payload["components"][0]["components"][0]["accessory"]["media"]["url"]

        self.assertNotIn("{{", serialized)
        self.assertTrue(image_url.endswith("/clothing_rack.png"))

    def test_render_reports_missing_values(self):
        with self.assertRaises(ComponentTemplateError) as context:
            render_template_payload("item", {"item_name": "Clothing Rack"})

        self.assertIn("Missing template values", str(context.exception))
        self.assertIn("item_image_url", str(context.exception))

    def test_render_rejects_blank_source_values(self):
        values = {
            name: name.replace("_", " ")
            for name in template_placeholders("item")
        }
        values["item_wiki_url"] = ""

        with self.assertRaises(ComponentTemplateError) as context:
            render_template_payload("item", values)

        self.assertIn("item_wiki_url", str(context.exception))

    def test_moderation_template_preserves_numeric_accent_color(self):
        values = {
            name: name.replace("_", " ")
            for name in template_placeholders("moderation_incident")
        }
        values["accent_color"] = 15158332

        payload = render_template_payload("moderation_incident", values)
        container = payload["components"][0]

        self.assertEqual(container["type"], 17)
        self.assertEqual(container["accent_color"], 15158332)
        self.assertIn("{{", str(load_template_payload("moderation_incident")))

    def test_message_deleted_template_requires_a_reason(self):
        values = {
            name: name.replace("_", " ")
            for name in template_placeholders("moderation_message_deleted")
        }
        values["accent_color"] = 15158332

        payload = render_template_payload("moderation_message_deleted", values)
        self.assertEqual(payload["components"][0]["accent_color"], 15158332)

        values["reason"] = ""
        with self.assertRaises(ComponentTemplateError) as context:
            render_template_payload("moderation_message_deleted", values)

        self.assertIn("reason", str(context.exception))

    def test_message_deleted_template_renders_safe_discord_mentions(self):
        values = {
            name: name.replace("_", " ")
            for name in template_placeholders("moderation_message_deleted")
        }
        values.update(
            accent_color=15158332,
            member_mention="<@123456789012345678>",
            channel_mention="<#987654321098765432>",
            timestamp_unix="1767657600",
        )

        payload = render_template_payload("moderation_message_deleted", values)
        text_displays = payload["components"][0]["components"]
        serialized = str(text_displays)

        self.assertEqual(payload["allowed_mentions"], {"parse": []})
        self.assertIn("<@123456789012345678>", serialized)
        self.assertIn("<#987654321098765432>", serialized)
        self.assertIn("<t:1767657600:f>", serialized)
        self.assertIn("<t:1767657600:R>", serialized)

    def test_automod_and_raid_templates_render_with_numeric_accent_colors(self):
        names = (
            "moderation_automod_timeout",
            "moderation_manual_action",
            "moderation_permission_error",
            "moderation_raid_detected",
            "moderation_raid_join_action",
        )
        for name in names:
            with self.subTest(template=name):
                values = {
                    key: key.replace("_", " ")
                    for key in template_placeholders(name)
                }
                values["accent_color"] = 15158332
                payload = render_template_payload(name, values)
                self.assertEqual(payload["components"][0]["accent_color"], 15158332)
