# Discord OAuth Account-Linking Contract

Status: proposed contract for the Babylon website/API developer and Discord bot developer.

## Goal

A user who is already signed into Babylon can prove ownership of a Discord
account and link the two identities. Discord OAuth is used only as identity
proof. Babylon remains the source of truth for the website account and the bot
never receives a Babylon password, website session, Capital Rift cookie, Discord
bot token, Discord client secret, or Discord user OAuth token.

This OAuth flow is separate from installing the Discord bot into a server.

## Discord application configuration

Use the same Discord application as the bot unless the team deliberately wants
a separate OAuth application.

Required server-side environment variables:

    DISCORD_CLIENT_ID=<public application id>
    DISCORD_CLIENT_SECRET=<secret; server-side only>
    DISCORD_REDIRECT_URI=https://holdings.thebabylon.hu/api/v1/auth/discord/callback
    BABYLON_DISCORD_SERVICE_TOKEN=<separate bot-to-API secret>

Register the redirect URI exactly in the Discord Developer Portal. Use separate
exact redirect URIs and secrets for local development, staging, and production.

Request only the Discord OAuth scope:

    identify

Do not request email, connections, guilds, guilds.join, bot, or
applications.commands for account linking unless a later feature has a
documented need. The identify scope is sufficient to call Discord's current-user
endpoint and obtain the immutable Discord user ID.

## User flow

1. The user signs into the Babylon website normally.
2. The user clicks Link Discord in Babylon account settings.
3. Babylon creates a random, single-use state value bound to the signed-in
   Babylon session and redirects the browser to Discord.
4. The user approves the identify scope.
5. Discord redirects to Babylon with code and state.
6. Babylon validates state before exchanging the code.
7. Babylon exchanges the code server-to-server for a Discord user access token.
8. Babylon calls Discord GET /api/v10/users/@me with that bearer token.
9. Babylon atomically stores the Babylon-user-to-Discord-user link.
10. Babylon discards the OAuth response and redirects to a success page.
11. The Discord bot can now resolve the user's Babylon account using the
    immutable Discord user ID received in interactions.

The callback must require the original authenticated Babylon session. Discord
OAuth must not silently become a separate Babylon login flow unless that is
designed and reviewed separately.

## Website endpoints

### Start OAuth

GET /api/v1/auth/discord/start

Authentication: normal Babylon website session.

Behavior:

- Generate at least 256 bits of cryptographically random state.
- Store only a hash of state when practical.
- Bind state to the Babylon session and intended redirect destination.
- Expire state within 10 minutes and allow it to be used once.
- Return a 302 redirect to Discord:

    https://discord.com/oauth2/authorize
      ?response_type=code
      &client_id=<DISCORD_CLIENT_ID>
      &scope=identify
      &state=<random-state>
      &redirect_uri=<exact-url-encoded-callback>

Do not accept an arbitrary redirect URI from the browser.

### OAuth callback

GET /api/v1/auth/discord/callback?code=<code>&state=<state>

Authentication: the same Babylon website session that started the flow.

Required processing order:

1. Reject missing, expired, reused, or session-mismatched state.
2. Mark state consumed atomically.
3. Exchange code at Discord POST /api/oauth2/token.
4. Send the token request as application/x-www-form-urlencoded, not JSON.
5. Authenticate with the Discord client ID and client secret.
6. Call Discord GET /api/v10/users/@me with Authorization: Bearer <access token>.
7. Verify a nonempty Discord id was returned.
8. Create the link in one database transaction.
9. Discard access_token and refresh_token. Long-term Discord authorization is
   unnecessary for identity-only linking.
10. Redirect to a fixed Babylon success or error page.

Token exchange form fields:

    grant_type=authorization_code
    code=<callback code>
    redirect_uri=<exact registered callback>

If the team wants the Discord authorization itself removed immediately after
identity verification, revoke the token at POST /api/oauth2/token/revoke after
the link transaction succeeds. This is optional when tokens are never stored,
but token revocation is the cleanest identity-only design.

### Read the signed-in user's link

GET /api/v1/me/discord-link

Authentication: normal Babylon website session.

Successful response:

    {
      "linked": true,
      "discord": {
        "id": "521677550456537088",
        "username": "example",
        "globalName": "Example User",
        "avatarUrl": "https://cdn.discordapp.com/..."
      },
      "linkedAt": "2026-09-02T12:04:00Z"
    }

Return {"linked": false} when no link exists.

### Unlink from the website

DELETE /api/v1/me/discord-link

Authentication: normal Babylon website session plus normal CSRF protection.

Return 204 No Content after deletion. Consider requiring recent
reauthentication for higher account-security assurance.

## Bot-to-Babylon endpoints

These endpoints are not Discord OAuth endpoints. They let the Discord bot query
the established link using a dedicated, rotatable service credential:

    Authorization: Bearer <BABYLON_DISCORD_SERVICE_TOKEN>

### Resolve a Discord identity

GET /api/v1/discord/links/{discordUserId}

Successful response:

    {
      "linked": true,
      "account": {
        "id": "babylon-account-id",
        "displayName": "Example User"
      },
      "permissions": ["portfolio:read"],
      "linkedAt": "2026-09-02T12:04:00Z"
    }

Return 404 with error code DISCORD_NOT_LINKED when no link exists. Never return
email addresses, password data, browser/session tokens, Capital Rift cookies,
OAuth access tokens, OAuth refresh tokens, or internal credentials.

### Unlink from Discord

DELETE /api/v1/discord/links/{discordUserId}

Authentication: bot service credential.

The bot must require an ephemeral /unlink confirm:true interaction and ensure
the path Discord ID equals the interaction user's Discord ID. Return 204 No
Content after deletion.

## Database rules

Recommended logical fields:

    babylon_user_id         unique, foreign key
    discord_user_id         unique, string/varchar
    discord_username        display snapshot only
    discord_global_name     nullable display snapshot
    discord_avatar_hash     nullable display snapshot
    linked_at
    updated_at

Treat Discord IDs as strings in JSON and JavaScript to avoid integer precision
loss. The immutable discord_user_id is the identity key; usernames and display
names are not identifiers and may change.

Initially enforce one Discord account per Babylon account and one Babylon
account per Discord account. Handle both uniqueness checks in the same
transaction so concurrent callbacks cannot create conflicting links.

## Error contract

Use stable machine-readable errors:

    {
      "error": {
        "code": "DISCORD_OAUTH_STATE_INVALID",
        "message": "The Discord linking request expired or is invalid."
      }
    }

Recommended codes:

- DISCORD_OAUTH_DENIED
- DISCORD_OAUTH_STATE_INVALID
- DISCORD_OAUTH_EXCHANGE_FAILED
- DISCORD_IDENTITY_FAILED
- DISCORD_ALREADY_LINKED
- BABYLON_ACCOUNT_ALREADY_LINKED
- DISCORD_NOT_LINKED
- SERVICE_UNAUTHORIZED
- RATE_LIMITED

Show users short messages. Do not return Discord's raw token response or
internal exception text.

## Security requirements

- HTTPS only.
- Exact redirect URI allowlist; never allow an arbitrary callback URL.
- Cryptographically random, session-bound, single-use state with a short expiry.
- CSRF protection on unlinking and other website mutations.
- Rate limits on start, callback failure, bot resolution, and unlink endpoints.
- Never put the client secret, service token, access token, or refresh token in
  frontend JavaScript, URLs, Discord messages, analytics, or logs.
- Store the Discord client secret and bot service token in the hosting
  platform's protected environment variables.
- Do not persist Discord OAuth tokens for identity-only linking.
- Audit link creation, uniqueness conflicts, unlinking, and repeated failures
  without logging codes or tokens.
- Preserve the Babylon account session boundary: a Discord identity cannot
  choose which Babylon account it links to after OAuth begins.
- Provide users a website unlink control and an ephemeral Discord unlink
  command.
- Account linking grants read-only portfolio access initially. Trading requires
  a separate explicit authorization and confirmation design.

## Acceptance tests

- A signed-in Babylon user can link the Discord account returned by /users/@me.
- Missing, expired, reused, and session-mismatched state values fail.
- An OAuth callback without the original Babylon session fails.
- An arbitrary redirect URI cannot be injected.
- Two concurrent callbacks cannot bypass either uniqueness constraint.
- A Discord username change does not break the link.
- No OAuth or service credential is persisted in the link table or logged.
- Website and Discord unlink operations remove access immediately.
- The bot receives only the minimal linked-account response.
