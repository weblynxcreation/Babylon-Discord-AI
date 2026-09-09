# Components V2 Style Guide

## Structure

- Use one gold-accent Container as the outer component.
- Use a Section for the heading whenever an image is available.
- Put the item Thumbnail in the Section accessory so Discord renders it at the top right.
- Use Text Displays for content and small Separators between major sections.
- Keep messages below Discord's 40-component and 4,000-display-character limits.

## Images

Use a public HTTPS URL supplied by item data. Current wiki icons follow this convention:

`https://wiki.capitalrift.com/icons/{{item_slug}}.png`

Every Thumbnail needs descriptive alt text. Do not place a local filesystem path in a Discord payload.

## Copy

- Lead with the item or result name.
- Keep labels short and units explicit.
- Use code blocks for aligned numeric data.
- Put assumptions and data freshness in small footer text.
- Disable mention parsing unless a command explicitly needs mentions.
