"""Exercise ./bilibi connect-servers with a real Git application, a scripted gh, browser and ssh.

gh answers from a JSON file that stands in for GitHub and records every call.
The browser plays the owner's part: it loads the local page, reads the form that
would go to GitHub, and returns to the redirect URL with a code, as GitHub does
after the owner chooses "Create GitHub App". ssh stands in for each server's
install-server.sh and records the command and its standard input.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
PEM = '-----BEGIN RSA PRIVATE KEY-----\nnot-a-real-key\n-----END RSA PRIVATE KEY-----\n'

FAKE_GH = r'''
import json, os, sys
state_path = os.environ['FAKE_GITHUB']
github = json.load(open(state_path))
args = sys.argv[1:]
stdin = None if sys.stdin.isatty() else sys.stdin.read()
github['calls'].append({'args': args, 'stdin': stdin})

def finish(output=None, code=0, error=''):
    json.dump(github, open(state_path, 'w'))
    if output is not None:
        print(json.dumps(output))
    if error:
        print(error, file=sys.stderr)
    sys.exit(code)

def option(name):
    return args[args.index(name) + 1]

if args[0] in github.get('failing', []):
    finish(code=1, error='gh: Resource not accessible (HTTP 403)')
if args[0] == 'api':
    path = args[-1]
    if path == 'user':
        finish(github['user'])
    if path.startswith('users/'):
        account = github['accounts'].get(path.removeprefix('users/'))
        finish(account) if account else finish(code=1, error='gh: Not Found (HTTP 404)')
    if '--method' in args and path.startswith('app-manifests/'):
        finish(github['app'])
    if '/actions/variables/' in path:
        repository, name = path.removeprefix('repos/').split('/actions/variables/')
        value = github['variables'].get(repository, {}).get(name)
        finish({'name': name, 'value': value}) if value is not None else finish(code=1, error='gh: Not Found (HTTP 404)')
    if path.startswith('repos/'):
        facts = github['repositories'].get(path.removeprefix('repos/'))
        finish(facts) if facts else finish(code=1, error='gh: Not Found (HTTP 404)')
if args[:2] == ['variable', 'set']:
    github['variables'].setdefault(option('--repo'), {})[args[2]] = option('--body')
    finish()
finish(code=2, error=f'fake gh: unexpected call {args}')
'''

FAKE_BROWSER = r'''
import json, os, re, sys, html, urllib.request
from urllib.parse import parse_qs, urlsplit
url = sys.argv[1]
with open(os.environ['BROWSER_LOG'], 'a') as log:
    log.write(url + '\n')
if url.startswith('http://127.0.0.1:'):
    page = urllib.request.urlopen(url).read().decode()
    action = html.unescape(re.search(r'action="([^"]+)"', page)[1])
    manifest = json.loads(html.unescape(re.search(r'name="manifest" value="([^"]+)"', page)[1]))
    json.dump({'action': action, 'manifest': manifest, 'page': page}, open(os.environ['BROWSER_FORM'], 'w'))
    state = parse_qs(urlsplit(action).query)['state'][0]
    code = json.load(open(os.environ['FAKE_GITHUB']))['code']
    urllib.request.urlopen(f'{manifest["redirect_url"]}?code={code}&state={state}')
'''

# Each server answers from FAKE_SERVERS: {target: {"check": [code, out, err], "save": [code, out, err]}}.
FAKE_SSH = r'''
import json, os, shlex, sys
path = os.environ['FAKE_SERVERS']
servers = json.load(open(path))
args = sys.argv[1:]
assert args[:3] == ['-o', 'BatchMode=yes', '--'], args
target, remote = args[3], args[4]
words = shlex.split(remote)
stdin = sys.stdin.read()
servers.setdefault('calls', []).append({'argv': args, 'words': words, 'stdin': stdin})
json.dump(servers, open(path, 'w'))
answer = servers.get(target)
if answer is None:
    print(f'ssh: Could not resolve hostname {target}', file=sys.stderr)
    sys.exit(255)
code, out, err = answer['check' if '--check' in words else 'save']
print(out)
print(err, file=sys.stderr)
sys.exit(code)
'''

READY = [1, '', 'install-server: No GitHub App is set up on this server (/opt/bilibi/github-app.json).']
SAVED = [0, 'GitHub App Iv23liServers saved in /opt/bilibi/github-app.json for acme/shop. It can read acme/shop '
            '(repository 77) and cannot change anything.', '']


class ConnectServersTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='bilibi-connect-servers-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tools = self.root / 'bin'
        tools.mkdir()
        for name, body in (('gh', FAKE_GH), ('ssh', FAKE_SSH)):
            (tools / name).write_text(f'#!{sys.executable}\n{body}')
            (tools / name).chmod(0o755)
        browser = self.root / 'browser'
        browser.write_text(f'#!{sys.executable}\n{FAKE_BROWSER}')
        browser.chmod(0o755)
        self.state = self.root / 'github.json'
        self.servers_file = self.root / 'servers.json'
        self.form = self.root / 'form.json'
        self.opened = self.root / 'opened'
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith('GIT_') and key not in
                    ('BILIBI_SOURCE_DIR', 'BILIBI_BUILD_DIR', 'CARGO_TARGET_DIR', 'CI', 'GITHUB_ACTIONS')}
        self.env.update(GIT_CONFIG_GLOBAL=str(self.root / 'gitconfig'), GIT_CONFIG_NOSYSTEM='1',
                        GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.test',
                        GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.test',
                        PATH=f'{tools}{os.pathsep}{self.env["PATH"]}', BROWSER=str(browser),
                        FAKE_GITHUB=str(self.state), FAKE_SERVERS=str(self.servers_file),
                        BROWSER_FORM=str(self.form), BROWSER_LOG=str(self.opened))
        self.app = self.root / 'application'
        self.app.mkdir()
        shutil.copy2(ROOT / 'bilibi', self.app)
        shutil.copy2(ROOT / '.gitignore', self.app)
        shutil.copytree(ROOT / 'scripts', self.app / 'scripts', ignore=shutil.ignore_patterns('__pycache__', 'node_modules'))
        (self.app / 'setup.toml').write_text('format = 1\ntargets = ["x86_64-unknown-linux-gnu"]\n\n[platform]\n'
                                             f'url = "https://github.com/BelimbingProject/bilibi.git"\ncommit = "{"a" * 40}"\n')
        self.git('init', '-b', 'main')
        self.git('add', '.')
        self.git('commit', '-m', 'Application')
        self.git('remote', 'add', 'origin', 'git@github.com:acme/shop.git')
        self.github({
            'calls': [], 'code': 'one-time-code', 'failing': [],
            'user': {'login': 'owner-person'},
            'accounts': {'acme': {'login': 'acme', 'id': 900, 'type': 'Organization'}},
            'repositories': {'acme/shop': {'full_name': 'acme/shop', 'id': 77, 'private': True,
                                           'owner': {'login': 'acme', 'id': 900, 'type': 'Organization'}}},
            'variables': {},
            'app': {'slug': 'shop-servers-1a2b3c', 'client_id': 'Iv23liServers', 'pem': PEM,
                    'owner': {'login': 'acme'}, 'html_url': 'https://github.com/apps/shop-servers-1a2b3c'},
        })
        self.serve({'admin@dev.example.com': {'check': READY, 'save': SAVED},
                    'admin@staging.example.com': {'check': READY, 'save': SAVED}})

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.app), *args], env=self.env, text=True,
                                       stderr=subprocess.DEVNULL).strip()

    def github(self, value=None):
        if value is not None:
            self.state.write_text(json.dumps(value))
        return json.loads(self.state.read_text())

    def serve(self, value=None):
        if value is not None:
            self.servers_file.write_text(json.dumps(value))
        return json.loads(self.servers_file.read_text())

    def change(self, edit):
        state = self.github()
        edit(state)
        self.github(state)

    def command(self, *servers, ok=True, **extra):
        arguments = [argument for server in servers for argument in ('--server', server)]
        result = subprocess.run([str(self.app / 'bilibi'), 'connect-servers', *arguments], env={**self.env, **extra},
                                cwd=self.root, input='\n', capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0 if ok else 1, result.stdout + result.stderr)
        output = result.stdout + result.stderr
        self.assertNotIn('not-a-real-key', output)
        return output

    def ssh_calls(self):
        return self.serve().get('calls', [])

    def saves(self):
        return [call for call in self.ssh_calls() if '--check' not in call['words']]

    def refused_before_anything(self, *servers, expected, **extra):
        variables = self.github()['variables']
        output = self.command(*servers, ok=False, **extra)
        for text in expected:
            self.assertIn(text, output)
        self.assertFalse(self.form.exists())
        self.assertEqual(self.saves(), [])
        self.assertEqual(self.github()['variables'], variables)
        return output

    def test_creates_the_app_opens_the_install_page_and_puts_the_key_on_each_server(self):
        output = self.command('admin@dev.example.com', 'admin@staging.example.com')
        form = json.loads(self.form.read_text())
        action = urlsplit(form['action'])
        self.assertEqual(f'{action.scheme}://{action.netloc}{action.path}', 'https://github.com/organizations/acme/settings/apps/new')
        manifest = form['manifest']
        # Read-only release files and their provenance, no webhook, installable only on acme.
        self.assertEqual(manifest['default_permissions'], {'contents': 'read', 'attestations': 'read'})
        self.assertEqual(manifest['default_events'], [])
        self.assertIs(manifest['hook_attributes']['active'], False)
        self.assertIs(manifest['public'], False)
        self.assertLessEqual(len(manifest['name']), 34)
        self.assertIn('servers', manifest['name'])
        self.assertIn('can only read the releases of acme/shop', form['page'])
        # The install page names exactly the application repository.
        install = self.opened.read_text().splitlines()[-1]
        address = urlsplit(install)
        self.assertEqual(address.path, '/apps/shop-servers-1a2b3c/installations/new/permissions')
        self.assertEqual(parse_qs(address.query), {'target_id': ['900'], 'repository_ids[]': ['77']})
        # Each server was checked first, then received the key on standard input only.
        calls = self.ssh_calls()
        self.assertEqual([call['argv'][3] for call in calls], ['admin@dev.example.com', 'admin@staging.example.com'] * 2)
        self.assertEqual([call['words'] for call in calls[:2]], [['sudo', '-n', 'scripts/install-server.sh', 'github-app', '--check']] * 2)
        for call in calls[2:]:
            self.assertEqual(call['words'], ['sudo', '-n', 'scripts/install-server.sh', 'github-app',
                                             '--client-id', 'Iv23liServers', '--repo', 'acme/shop'])
            self.assertEqual(call['stdin'], PEM)
        self.assertFalse(any('not-a-real-key' in ' '.join(call['argv']) for call in calls))
        self.assertFalse(any('not-a-real-key' in ' '.join(call['args']) for call in self.github()['calls']))
        self.assertEqual(self.github()['variables'], {'acme/shop': {'SERVER_APP_CLIENT_ID': 'Iv23liServers'}})
        for text in ('Only select repositories', 'admin@dev.example.com: GitHub App Iv23liServers saved',
                     'admin@staging.example.com: GitHub App', 'not written to disk', install):
            self.assertIn(text, output)
        # Nothing new in the application and no key file anywhere.
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=all'), '')
        self.assertFalse([path for path in self.root.rglob('*') if path.is_file()
                          and path not in (self.state, self.servers_file)
                          and 'not-a-real-key' in path.read_text(errors='ignore')])

    def test_a_server_path_can_be_given(self):
        self.serve({'admin@dev.example.com': {'check': READY, 'save': SAVED}})
        self.command('admin@dev.example.com:/srv/bilibi-tools/scripts/install-server.sh')
        self.assertEqual({call['words'][2] for call in self.ssh_calls()}, {'/srv/bilibi-tools/scripts/install-server.sh'})

    def test_public_repository_needs_nothing(self):
        self.change(lambda github: github['repositories']['acme/shop'].update(private=False))
        output = self.command('admin@dev.example.com')
        self.assertIn('is public, so servers read its releases without a GitHub App', output)
        self.assertEqual(self.ssh_calls(), [])
        self.assertFalse(self.opened.exists())

    def test_a_server_is_required(self):
        self.refused_before_anything(expected=['Name each server to connect'])

    def test_an_ssh_option_is_not_a_server(self):
        self.refused_before_anything('-oProxyCommand=touch /tmp/x', expected=['is not a server'])
        self.assertEqual(self.ssh_calls(), [])

    def test_unreachable_server_stops_before_the_app_is_created(self):
        self.refused_before_anything('admin@dev.example.com', 'admin@gone.example.com',
                                     expected=['admin@gone.example.com: could not run sudo -n', 'Nothing was changed'])

    def test_server_tools_without_github_app_stop_before_the_app_is_created(self):
        self.serve({'admin@dev.example.com': {'check': [2, '', 'usage: install-server.sh create ...'], 'save': SAVED}})
        self.refused_before_anything('admin@dev.example.com', expected=['has no github-app command yet'])

    def test_an_existing_app_is_not_replaced(self):
        self.change(lambda github: github['variables'].update({'acme/shop': {'SERVER_APP_CLIENT_ID': 'Iv23liOld'}}))
        output = self.refused_before_anything('admin@dev.example.com', expected=[
            'already has a server GitHub App (client ID Iv23liOld)',
            'github-app --client-id Iv23liOld --repo acme/shop', 'gh variable delete SERVER_APP_CLIENT_ID'])
        self.assertNotIn('Opening your browser', output)

    def test_another_persons_account_is_refused(self):
        self.change(lambda github: github['accounts']['acme'].update(type='User'))
        self.refused_before_anything('admin@dev.example.com', expected=['Only acme can create a GitHub App'])

    def test_failed_save_says_how_to_finish(self):
        self.serve({'admin@dev.example.com': {'check': READY, 'save': SAVED},
                    'admin@staging.example.com': {'check': READY, 'save': [1, '', 'install-server: no instance exists yet']}})
        output = self.command('admin@dev.example.com', 'admin@staging.example.com', ok=False)
        for text in ('admin@dev.example.com: GitHub App Iv23liServers saved', 'admin@staging.example.com: the App was not saved',
                     'no instance exists yet', 'https://github.com/organizations/acme/settings/apps/shop-servers-1a2b3c',
                     'generate a private key', 'github-app --client-id Iv23liServers --repo acme/shop'):
            self.assertIn(text, output)

    def test_app_created_for_another_owner_is_not_sent_to_servers(self):
        self.change(lambda github: github['app']['owner'].update(login='owner-person'))
        output = self.command('admin@dev.example.com', ok=False)
        self.assertIn('belongs to owner-person, not acme', output)
        self.assertEqual(self.saves(), [])
        self.assertEqual(self.github()['variables'], {})

    def test_ci_is_refused(self):
        self.refused_before_anything('admin@dev.example.com', expected=['opens GitHub in your browser'], CI='true')

    def test_help_lists_the_command(self):
        result = subprocess.run([str(self.app / 'bilibi'), 'help'], env=self.env, capture_output=True, text=True)
        self.assertIn('  connect-servers --server <user@host>\n', result.stdout)


if __name__ == '__main__':
    unittest.main()
