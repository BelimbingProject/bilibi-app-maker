"""./bilibi connect-servers: let servers read the application's private releases without a token that expires.

A server installs releases from the application repository: the terminal
install checks the pinned release proof, and Software › Releases lists,
downloads and checks releases. For a private repository this command creates
a GitHub App that only the owner can install, with two read-only permissions
(Contents and Attestations), opens its install page for exactly the
application repository, and sends the App's private key over ssh into
install-server.sh github-app on each server, which checks it and keeps it
root-only. Each later install mints a token from the App that reads only this
repository and expires within the hour, so nobody renews a token. The private
key goes from GitHub to ssh's input in memory: it is never written to disk or
printed.
"""
import re
import secrets
import shlex
import shutil
import subprocess
from urllib.parse import urlencode
import webbrowser

import private_sources
from private_sources import gh, gh_json, variable

COMMAND = './bilibi connect-servers'
GUIDE = 'docs/guides/connecting-servers.md'
# Remembers the App for the next run; the client ID is not a secret.
CLIENT_ID = 'SERVER_APP_CLIENT_ID'
DEFAULT_SCRIPT = 'scripts/install-server.sh'
# user@host or host, then optionally :/path/to/install-server.sh. Never an ssh option.
SERVER = re.compile(r'^((?:[A-Za-z0-9._-]+@)?[A-Za-z0-9][A-Za-z0-9.-]*)(?::(\S+))?$')


def servers(given):
    """(ssh target, install-server.sh path) for each --server."""
    if not given:
        raise ValueError(f'Name each server to connect: {COMMAND} --server admin@erp.example.com '
                         f'[--server admin@staging.example.com]. Nothing was changed.')
    found = []
    for value in given:
        match = SERVER.fullmatch(value)
        if not match:
            raise ValueError(f'{value} is not a server: use user@host, or user@host:/path/to/install-server.sh '
                             f'when the server tools are not in {DEFAULT_SCRIPT} of that login. Nothing was changed.')
        found.append((match[1], match[2] or DEFAULT_SCRIPT))
    return found


def ssh(target, script, *args, stdin=None):
    """Run install-server.sh on the server with sudo; return (exit code, output, errors)."""
    remote = ' '.join(shlex.quote(word) for word in ('sudo', '-n', script, *args))
    # BatchMode: never stop to ask for a password; the key, when given, is the only input.
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '--', target, remote], input=stdin or '',
                            capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def ready(target, script):
    """Refuse before anything is created when a server cannot take the App."""
    code, out, errors = ssh(target, script, 'github-app', '--check')
    if code == 0:
        return f'{target} already reads with a GitHub App ({out}); it gets the new one.'
    if code == 1 and 'install-server:' in errors:
        return None
    if code == 2:
        raise ValueError(f'{target}: {script} has no github-app command yet. Update the server tools from a newer '
                         f'release first (see "Private application repositories" in the Platform\'s docs/server-install.md). Nothing was changed.')
    raise ValueError(f'{target}: could not run sudo -n {script} over ssh ({errors or f"exit {code}"}). Check that ssh '
                     f'{target} works without a password prompt and that this login may run the script with sudo -n, '
                     f'or give its path as --server {target}:/path/to/install-server.sh. Nothing was changed.')


def manifest(repository, redirect):
    owner, name = repository.split('/')
    home = f'https://github.com/{repository}'
    return {
        # App names are unique across GitHub and at most 34 characters: ' servers ' and 6 hex digits take 15, leaving 19.
        'name': f'{name[:19].rstrip("-_.")} servers {secrets.token_hex(3)}',
        'url': home,
        'description': f'Lets the servers of {repository} read its releases and their build provenance.',
        # No webhook: the App only mints read tokens for the servers.
        'hook_attributes': {'url': home, 'active': False},
        'redirect_url': redirect,
        # Installable only on the account that owns it.
        'public': False,
        # Release files and their build provenance, read-only. Nothing else.
        'default_permissions': {'contents': 'read', 'attestations': 'read'},
        'default_events': [],
    }


def connect(repository, given):
    if not shutil.which('gh'):
        raise ValueError(f'Install the GitHub CLI (gh) and sign in with gh auth login, then rerun {COMMAND}.')
    targets = servers(given)
    owner = repository.split('/')[0]
    facts = gh_json(f'repos/{repository}')
    if facts is None:
        raise ValueError(f'Cannot see {repository} with your GitHub sign-in; check gh auth status, then rerun {COMMAND}.')
    if not facts['private']:
        print(f'{repository} is public, so servers read its releases without a GitHub App. Nothing was changed.')
        return
    existing = variable(repository, CLIENT_ID)
    if existing:
        raise ValueError(f'{repository} already has a server GitHub App (client ID {existing}). To connect another '
                         f'server, generate a private key on the App settings page and run: ssh <server> sudo '
                         f'{DEFAULT_SCRIPT} github-app --client-id {existing} --repo {repository} < <downloaded .pem>, '
                         f'then delete the downloaded file ({GUIDE}). To start again with a new App, run gh variable '
                         f'delete {CLIENT_ID} --repo {repository}, then rerun {COMMAND}.')
    account = gh_json(f'users/{owner}')
    signed_in = gh_json('user')
    if account is None or signed_in is None:
        raise ValueError(f'Cannot look up {owner} on GitHub; check gh auth status, then rerun {COMMAND}.')
    if account['type'] != 'Organization' and signed_in['login'].lower() != owner.lower():
        raise ValueError(f'Only {owner} can create a GitHub App for their account; you are signed in to gh as '
                         f'{signed_in["login"]}. Ask {owner} to run {COMMAND}. Nothing was changed.')
    # Every server is checked first, so an unreachable one stops before an App exists.
    for target, script in targets:
        note = ready(target, script)
        if note:
            print(note)
    app = private_sources.created_app(
        repository, account['type'], lambda redirect: manifest(repository, redirect),
        f'Bilibi creates a GitHub App that can only read the releases of {repository}.', COMMAND)
    settings = (f'https://github.com/organizations/{owner}/settings/apps/{app["slug"]}' if account['type'] == 'Organization'
                else f'https://github.com/settings/apps/{app["slug"]}')
    install = (f'https://github.com/apps/{app["slug"]}/installations/new/permissions?'
               + urlencode([('target_id', account['id']), ('repository_ids[]', facts['id'])]))
    key = app.pop('pem')
    if app['owner']['login'].lower() != owner.lower():
        raise ValueError(f'The new App {app["slug"]} belongs to {app["owner"]["login"]}, not {owner}, so it cannot be '
                         f'installed on {repository}. Delete it in the GitHub App settings of {app["owner"]["login"]}, '
                         f'then rerun {COMMAND} and keep {owner} as the owner. Nothing was sent to a server.')
    if not gh('variable', 'set', CLIENT_ID, '--repo', repository, '--body', app['client_id'])[0]:
        print(f'Note: {CLIENT_ID} was not set in {repository} (gh said why above), so a rerun will not know this App. '
              f'Set it with gh variable set {CLIENT_ID} --repo {repository} --body {app["client_id"]}.')
    print(f'Created the GitHub App {app["slug"]} (client ID {app["client_id"]}).\n'
          f'Next, in your browser: install it on {owner}, choose "Only select repositories", and select only '
          f'{repository}. If the page does not open, visit {install}', flush=True)
    webbrowser.open(install)
    try:
        input('Press Enter after you choose "Install". ')
    except EOFError:
        pass
    failed = []
    for target, script in targets:
        code, out, errors = ssh(target, script, 'github-app', '--client-id', app['client_id'],
                                '--repo', repository, stdin=key)
        if code == 0:
            print(f'{target}: {out}')
        else:
            failed.append(target)
            print(f'{target}: the App was not saved ({errors or f"exit {code}"}).')
    key = None
    if failed:
        raise ValueError(f'The key GitHub sent was not saved anywhere else. For {", ".join(failed)}: on {settings}, '
                         f'generate a private key, run ssh <server> sudo {DEFAULT_SCRIPT} github-app --client-id '
                         f'{app["client_id"]} --repo {repository} < <downloaded .pem>, then delete the downloaded file.')
    print(f'Done. Each install and each Software › Releases check now gets a new read-only token for {repository} '
          f'from the App, so no token has to be renewed. The private key was not written to disk on this computer.')
