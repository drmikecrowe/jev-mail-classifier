# Privacy Policy

jev-mail is a command-line tool that you run on your own computer. It sorts your email into categories. This policy says what it does with your data.

## Who runs it

Each person who uses jev-mail runs their own copy and creates their own Google Cloud project and OAuth client for Gmail access. The authors of jev-mail run no server for it and receive none of your data.

## What it reads

jev-mail reads the email in the accounts you configure: the sender, subject, headers and body of each message. It needs this to put each message in a category.

## Where your data goes

- **To the classifier you choose.** For a message that the local rules cannot decide, jev-mail sends its subject and body (up to 20,000 characters) to the Jev provider you configure: TypeSafe, OpenRouter or Vercel AI Gateway. That provider's own privacy policy applies to what it receives.
- **To a webhook, only if you add one.** A `webhook` action sends the category, the probability and the subject to the URL you set.
- **To your mail provider.** jev-mail asks Gmail, Microsoft 365 or your IMAP server to label, move, flag or mark your messages, as your configuration says.

jev-mail sends your data nowhere else. It has no analytics and no telemetry.

## What it stores

Everything it stores stays on your computer, beside `config.yaml`:

- `config.yaml` and `.env`: your settings and secrets.
- `gmail-token.json` and `o365-token.json`: the sign-in tokens for Gmail and Microsoft 365.
- `state.db`: one row per processed message, with its Message-ID, the category scores and the actions taken. It holds no message bodies.
- `senders.csv` and `sender-census.csv`: sender addresses and counts.

You can delete any of these files at any time. To remove jev-mail's access to Gmail, delete `gmail-token.json` and revoke the app at <https://myaccount.google.com/permissions>.

## Google user data

jev-mail's use of information received from Google APIs follows the [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including the Limited Use requirements. It uses Gmail data only to sort your own mailbox for you, and transfers it only to the classifier you choose, as described above.

## Changes

Changes to this policy are made in this file and recorded in the repository's history.
