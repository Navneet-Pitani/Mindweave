# Connect accounts and saved conversations

The supplied project URL and publishable key are configured in the ignored `.env` file. No service-role key is needed or used. Restart the Python server after changing `.env`.

1. Open your Supabase project's SQL Editor and run `supabase/schema.sql` once. The script creates only the `mw_profiles`, `mw_conversations`, and `mw_turns` application tables, their indexes, and owner-only row-level policies. Existing project tables are not changed.
2. In Authentication, enable Email sign-in and decide whether email confirmation is required. Configure the Site URL to your local app address while developing, and use the real HTTPS app URL when deploying.
3. Start `python -m mindweave.web`, visit `/login`, and create an account. If email confirmation is enabled, confirm the email and then sign in.
4. Turn on **Save future chats to Supabase** before a conversation you want to retain. A new conversation starts at each change of this setting. Previous unsaved messages are not uploaded implicitly.
5. Use **Saved conversations** to reopen or delete your own chats. Starting a new chat keeps previously saved chats. Signing out clears the local session and tokens.

## Storage

| Data | Location |
|---|---|
| Account email and password authentication | Supabase Auth (`auth.users`; passwords handled by Supabase, never stored in application tables) |
| Display name and saved intervention preferences | `public.mw_profiles`, one row per authenticated user |
| Conversation title and owner | `public.mw_conversations`, only when saving is enabled |
| User/assistant text, model results, and timestamps | `public.mw_turns`, only when saving is enabled |
| Unsaved conversation context | Python server memory, cleared on new chat, logout or server shutdown |
| Raw audio | Browser playback memory and transient server processing; never uploaded to Supabase |
| Login tokens | Server memory, accessed by an HttpOnly, SameSite browser session cookie; not browser localStorage |

The backend sends the authenticated user's JWT with every database request. Row-level security checks `auth.uid() = user_id`; a composite foreign key also prevents assigning a turn to another user's conversation. A publishable key alone does not grant access to anyone's chat history. These tables are readable by authorized Supabase project administrators; this is cloud storage, not end-to-end encryption.

Applying the SQL and testing two real accounts are necessary to verify the live deployment. Local tests with a simulated provider do not verify your project's real policies. The app is served over HTTP bound only to loopback for development. Before deployment use HTTPS, Secure cookies, production session storage/rate limits, and review the authentication lifecycle.

Schema can be applied by a project administrator in the SQL Editor. A publishable key cannot create database tables; do not replace it with a service-role key to try to do so.

## Signup troubleshooting

The login form shows a safe provider error code in square brackets. Do not share passwords or tokens when reporting failures.

- `email_address_not_authorized`: the built-in mail service cannot deliver to this address. Configure custom SMTP in Supabase's email settings.
- `over_email_send_rate_limit`: wait for the sending limit to reset, or configure custom SMTP. Repeated signup attempts do not resolve the limit.
- `email_not_confirmed`: use the confirmation email before signing in.
- `weak_password`: follow the project's configured password-strength rules.
- `signup_disabled` or `email_provider_disabled`: check the corresponding Authentication setting.
- `captcha_failed`: the project requires CAPTCHA; this client needs that integration before signup can work.
- `unexpected_failure` or an unknown code: inspect the matching Authentication log entry in the Supabase dashboard. Raw provider bodies are deliberately not displayed, because they can contain private details.

Email signup and required email confirmation were verified enabled during the signup troubleshooting check. This does not establish successful email delivery or prove which error caused a prior attempt.

References: [Supabase Auth](https://supabase.com/docs/guides/auth), [row-level security](https://supabase.com/docs/guides/database/postgres/row-level-security), [user profiles](https://supabase.com/docs/guides/auth/managing-user-data).
