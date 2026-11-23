# Connecting servers

When your application repository is private, your servers need permission to read its releases, and one command gives it for good:

```sh
./bilibi connect-servers --server admin@dev.example.com --server admin@staging.example.com
```

```text
Opening your browser to create the GitHub App. If it does not open, visit http://127.0.0.1:43117/
On GitHub, check the App is for your-company, then choose "Create GitHub App".
Created the GitHub App my-bilibi-servers-1a2b3c (client ID Iv23li0a1b2c3d4e5f6g).
Next, in your browser: install it on your-company, choose "Only select repositories", and select only your-company/my-bilibi. If the page does not open, visit https://github.com/apps/my-bilibi-servers-1a2b3c/installations/new/permissions?...
Press Enter after you choose "Install".
admin@dev.example.com: GitHub App Iv23li0a1b2c3d4e5f6g saved in /opt/bilibi/github-app.json for your-company/my-bilibi. It can read your-company/my-bilibi (repository 123456789) and cannot change anything.
admin@staging.example.com: GitHub App Iv23li0a1b2c3d4e5f6g saved in /opt/bilibi/github-app.json for your-company/my-bilibi. It can read your-company/my-bilibi (repository 123456789) and cannot change anything.
Done. Each install and each Software › Releases check now gets a new read-only token for your-company/my-bilibi from the App, so no token has to be renewed. The private key was not written to disk on this computer.
```

Notice what you did by hand: two clicks in the browser, "Create GitHub App" and "Install", and Enter in the terminal. The command created a GitHub App that can only read your application repository and put it on each server.

Notice also what did **not** happen: no token or key was printed or saved in a file, and nobody has to make a token again when one expires.

You may already have questions: what the servers do with the App, why it is safe to keep on a server, and how to add a server later. We cover each of these below.

This guide is about servers. For GitHub's own checks reading private Domains and Extensions, see [Private sources](private-sources.md).

## Before you start

You need:

- the GitHub CLI, `gh`, signed in with `gh auth login` as someone who administers your application repository;
- your application connected to its own GitHub repository as `origin` (see "Start here" in the [README](../../README.md));
- for a personal account, to be signed in as that account; for an organisation, permission to create GitHub Apps in it (organisation owners have it);
- each server already set up with `install-server.sh create`, and an ssh login that may run its server tools with `sudo` without a password prompt. Give the path when the tools are not in `scripts/install-server.sh` of that login: `--server admin@dev.example.com:/opt/bilibi-tools/scripts/install-server.sh`.

## What the command does

1. **Checks each server.** Over ssh it runs `sudo -n install-server.sh github-app --check`. A server it cannot reach, or whose server tools are too old to take an App, stops the command before anything is created.
2. **Creates the GitHub App.** Your browser opens GitHub's page for a new App, already filled in: no webhook, two permissions (**Contents: Read-only** and **Attestations: Read-only**), and installable only on your account. You check the name and owner and choose "Create GitHub App". GitHub then hands the App back to the command on your own computer.
3. **Opens the install page.** You install the App on your account, choose "Only select repositories", pick only your application repository, and press Enter in the terminal.
4. **Puts the App on each server.** The command sends the private key over ssh, on standard input, to `install-server.sh github-app --client-id <id> --repo <owner/name>`. The server checks the App against GitHub, keeps it in `/opt/bilibi/github-app.json` and prints what it can read.
5. **Remembers the App.** It sets the Actions variable `SERVER_APP_CLIENT_ID` in your application repository to the App client ID, so a second run knows the App exists. The client ID is not a secret.

To confirm it worked on a server later, run `sudo scripts/install-server.sh github-app --check` there, or open **Software › Releases**: **Read access** names the App.

## What the servers do with it

**Each check mints its own token, which reads only your application repository and expires within the hour.** The terminal install (`install-server.sh release`, `installer` and `verify`) hands it to GitHub CLI for one build-provenance check. **Software › Releases** uses one for each list, review, download and upload check. The token is never saved, so there is nothing to renew: installs and upgrades can run unattended.

## Why is it safe to keep on a server?

- The App can only read, and only the repository you installed it on. The server refuses an App that can change anything, or that is installed on all of your account's repositories.
- The key file can be read only by root and the Bilibi services, like each instance's `env` file, which already holds the key that unlocks saved secrets.
- One place revokes it: delete the App's private key on its settings page on GitHub.

## Adding another server later

When `SERVER_APP_CLIENT_ID` is already set, the command stops instead of creating a second App. GitHub never sends an existing key again, so give the new server a key of its own:

1. On the App settings page on GitHub, generate a new private key. Your browser downloads it as a `.pem` file.
2. Put it on the server: `ssh admin@new.example.com sudo scripts/install-server.sh github-app --client-id <client ID> --repo <owner/name> < downloaded.pem`.
3. Delete the downloaded file.

To start again with a new App, delete the variable with `gh variable delete SERVER_APP_CLIENT_ID` and run the command again.

## Replacing the private key

For example when someone who could read a server's files leaves:

1. On the App settings page on GitHub, generate a new private key.
2. Put it on each server as in [Adding another server later](#adding-another-server-later), step 2, then delete the downloaded file.
3. Back on the App settings page, delete the old private key, so it no longer works.

## If something goes wrong

The command stops with a message that says what happened and what to run next. Two cases need a word more:

- **The App was created, but a server did not take it**, for example because ssh failed. We never keep the key, so the message gives the App settings page: generate a private key there, put it on that server as in [Adding another server later](#adding-another-server-later), and delete the downloaded file.
- **You closed the browser before creating the App.** Nothing was changed; press Ctrl+C and run the command again.

## Setting it up by hand

The command does exactly these steps, which you can also do yourself:

1. Create a GitHub App owned by the account that owns the application repository: no webhook, repository permissions **Contents: Read-only** and **Attestations: Read-only**, installable only on that account.
2. Install it on the application repository only.
3. Generate a private key, run `sudo scripts/install-server.sh github-app --client-id <client ID> --repo <owner/name> < downloaded.pem` on each server, then delete the downloaded file.

## Where to go next

Return to [Installing a release](installing.md). The Platform's [server installation reference](https://github.com/BelimbingProject/bilibi/blob/main/docs/server-install.md#private-application-repositories) covers the server side.
