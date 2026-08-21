# Production Integrations

This document is the single setup path for Autopilot provider verification.

## 1. Deploy URLs first

Decide the public URLs before creating provider credentials:

```text
Frontend: https://app.your-domain.com
API:      https://api.your-domain.com
```

Set these production environment variables:

```env
FRONTEND_URL=https://app.your-domain.com
GMAIL_REDIRECT_URI=https://api.your-domain.com/api/integrations/gmail/callback
```

Do not use `localhost` after deployment.

## 2. Gmail OAuth

1. Open Google Cloud Console and create or select a project.
2. Configure the OAuth consent screen. Add your support email and production domain.
3. Add `https://app.your-domain.com` to **Authorized JavaScript origins**.
4. Create an OAuth client of type **Web application**.
5. Add this exact **Authorized redirect URI**:

```text
https://api.your-domain.com/api/integrations/gmail/callback
```

6. Enable the Gmail API for the project.
7. Add the following to the API environment, never the frontend:

```env
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REDIRECT_URI=https://api.your-domain.com/api/integrations/gmail/callback
INTEGRATION_ENCRYPTION_KEY=...
```

Generate the encryption key once:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The application asks Google only for `gmail.send`. A refresh token is encrypted server-side and never sent to the browser.

## 3. Twilio Verify

1. Create a Twilio account and complete its account verification.
2. In Twilio Console, open **Verify** and create a Verify Service.
3. Configure the service's SMS sender/geo permissions for the countries you support.
4. Add these API-only environment variables:

```env
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_VERIFY_SERVICE_SID=VA...
```

The phone flow accepts E.164 numbers, for example `+19195551234`. Twilio sends the code; the API marks the number verified only after Twilio returns `approved`.

## 4. Verify before launch

After deploying with the values above:

1. Sign in as a real production user.
2. Open **Autopilot** and select **Connect Gmail**.
3. Complete Google consent in the popup. The checklist should change to Done only after `/api/integrations/status` reports a connected Gmail record.
4. Select **Verify phone**, enter an E.164 phone number, then the received Twilio code.
5. Confirm the checklist shows Phone verified.
6. Test the email fallback on a browser without a desktop mail handler. It must show the copy/drag-in instructions instead of claiming a message was sent.

## 5. Operational constraints

- Google OAuth verification may be required before external customers can use restricted Gmail scopes.
- Twilio charges per verification. Set country permissions and fraud controls before opening to customers.
- Autopilot should continue to require explicit user approval for each application. A connected Gmail account is not permission to send unattended applications.
- Rotate Google, Twilio, and encryption secrets through the deployment provider; never commit them to this repository.
