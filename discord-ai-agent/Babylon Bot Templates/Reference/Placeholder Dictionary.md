# Placeholder Dictionary

Placeholders use `{{snake_case}}`. The renderer requires every placeholder in the selected template unless `strict=False` is explicitly requested.

## Shared

| Placeholder | Meaning | Example |
| --- | --- | --- |
| `item_name` | Display name | Clothing Rack |
| `item_id` | Stable item identifier | clothing_rack |
| `item_image_url` | Public HTTPS icon URL | https://wiki.capitalrift.com/icons/clothing_rack.png |
| `item_wiki_url` | Canonical public wiki page URL | https://wiki.capitalrift.com/<item-page> |
| `item_category` | Item grouping | Storage |
| `item_description` | Short user-facing description | Stores clothing and uniforms. |
| `machine_name` | Producing machine | Chip Fab |
| `updated_at` | Human-readable freshness value | just now |
| `data_quality` | Source verification or a source-data warning | -# ✓ Source fields verified. |
| `member_mention` | Discord user mention, built from the member's snowflake ID | `<@123456789012345678>` |
| `moderator_mention` | Discord user mention, built from the moderator's snowflake ID | `<@123456789012345678>` |
| `target_mention` | Discord user mention, built from the target's snowflake ID | `<@123456789012345678>` |
| `channel_mention` | Discord channel mention, built from the channel's snowflake ID | `<#123456789012345678>` |
| `timestamp_unix` | Unix timestamp in whole seconds | `1767657600` |

Mention fields are rendered as clickable Discord mentions. Moderation templates set `allowed_mentions.parse` to an empty list, so they do not notify users or channels.

## Discord timestamps

Moderation logs render each event as `<t:{{timestamp_unix}}:f>` for the viewer's localized date and time, plus `<t:{{timestamp_unix}}:R>` for relative time. Supply Unix time in seconds, never milliseconds. Discord supports `t`, `T`, `d`, `D`, `f`, `F`, and `R` style suffixes when another display is needed. [Timestamp syntax reference](https://gist.github.com/LeviSnoot/d9147767abeef2f770e9ddcd91eb85aa)

## Item command

`stack_size`, `base_value`, `market_price`, `availability_text`, `recipe_name`, `output_amount`, `cycle_time`, `output_rate`, `recipe_inputs`, `input_cost`, `output_value`, `profit_per_cycle`, `profit_per_minute`

## Agentic investment analysis

`accent_color`, `question`, `recommended_item`, `item_wiki_url`, `item_image_url`, `machine_name`, `machine_cost`, `profit_per_minute`, `profit_per_dollar`, `investment_outcome`, `comparison_visual`, `recommendation_reasoning`, `build_steps`, `constraints`, `source_attribution`, `timestamp_unix`, `data_quality`

`comparison_visual`, `recommendation_reasoning`, `build_steps`, and `constraints` must use Discord Markdown bullets or short paragraphs; Discord does not render Markdown tables. For `comparison_visual`, use one option per compact metric row with a labeled Unicode bar based only on verified values. Set `data_quality` to a source-data warning when current values, inputs, or compared alternatives are unavailable.

## Slash command confirmation

`result_title`, `command_name`, `result_details`, `next_step`, `timestamp_unix`, `data_quality`

## Slash command settings

`settings_title`, `settings_details`, `help_text`, `timestamp_unix`, `data_quality`

## Slash command error

`error_title`, `command_name`, `error_details`, `resolution`, `timestamp_unix`, `data_quality`

## Production line

`target_rate`, `recipe_name`, `output_per_cycle`, `cycle_time`, `recipe_inputs`, `input_cost`, `machine_count`, `production_math`, `input_rates`, `layout_sketch`, `storage_plan`

`layout_sketch` must show direct machine-to-machine item flow. Do not add conveyors, pipes, or any other transport entity unless it exists in the source data. Each line must be 44 characters or fewer; use short item labels in the sketch and place full machine names in `input_rates`.

## Moderation incident

`accent_color`, `severity_emoji`, `action_label`, `case_id`, `member_mention`, `rule_name`, `channel_mention`, `duration`, `source_system`, `evidence`, `timestamp_unix`, `data_quality`

## Moderation message deleted

`accent_color`, `member_mention`, `moderation_source`, `channel_mention`, `violation_number`, `rule_name`, `message_id`, `action_label`, `reason`, `timestamp_unix`, `case_id`, `data_quality`

## Automod timeout

`accent_color`, `member_mention`, `duration`, `violation_count`, `latest_violation`, `channel_mention`, `reason`, `timestamp_unix`, `case_id`, `data_quality`

## Raid detected

`accent_color`, `join_count`, `window_seconds`, `raid_action`, `minimum_account_age`, `raid_mode_status`, `next_step`, `timestamp_unix`, `case_id`, `data_quality`

## Raid join action

`accent_color`, `action_emoji`, `member_mention`, `member_id`, `account_age`, `minimum_account_age`, `action_label`, `raid_mode_status`, `reason`, `timestamp_unix`, `case_id`, `data_quality`

## Moderator action

`accent_color`, `action_emoji`, `action_label`, `moderator_mention`, `target_mention`, `channel_mention`, `duration_or_scope`, `reason`, `timestamp_unix`, `case_id`, `data_quality`

## Permission error

`accent_color`, `intended_action`, `target_mention`, `source_system`, `required_permission`, `channel_mention`, `reason`, `timestamp_unix`, `case_id`, `data_quality`
