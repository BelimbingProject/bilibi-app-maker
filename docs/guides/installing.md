# Installing a release

Install the same tested release on Staging and Production.

## Install a release

Set the Software page's **GitHub repository** setting to your own application repository, for example `your-company/my-bilibi`. The server reads its releases from that repository.

`./bilibi release` downloads the `bilibi-setup-v1.0.0-x86_64-unknown-linux-gnu.tar.gz` asset for you, checks it against `SHA256SUMS`, and prints its path and these steps. To fetch it again later, download that asset, `SHA256SUMS` and its `.proof.json` sidecar when the release has one. A GitHub-pinned server checks build provenance from your repository's `.github/workflows/release.yml`; an operator-pinned server checks the sidecar offline against its public key. A damaged file, a hand-uploaded replacement or an asset from the wrong repository, workflow, tag or target is refused and the running release stays in service.

On the target Bilibi instance, open **Software → Releases**, upload that archive and its sidecar when the server uses operator trust, review it, and confirm the install with a fresh 2FA code. For GitHub trust, leave the proof field empty. Keep the same downloaded archive and proof for Staging and Production. The existing installer handles backup, migration, switching, health checks, recovery and Undo.

GitHub's automatic **Source code** archives are not installable releases. The separate `bilibi-installer-x86_64-unknown-linux-gnu` and `bilibi-server-tools.tar.gz` assets are for initial server setup or deliberate administrator upgrades. Verify each one with the proof policy pinned on the server: either GitHub provenance for the application repository, workflow and exact setup tag, or its operator `.proof.json` and trusted public key. The Platform server-installation reference gives the complete commands. Ordinary application installs do not update the shared installer.

**A release over 64 MiB cannot be uploaded.** The build says so when it packages one, and `./bilibi release` then prints the GitHub steps instead: on **Software → Releases** choose **Refresh**, then **Review** on the release, and the server downloads it from GitHub. `install-server.sh release` on the server takes a file of any size.

An uploaded file must satisfy the server's pinned release-proof policy too. Set and accept the application repository on the Software page before uploading, and include the sidecar when it uses operator trust.

## A private application repository

Run `./bilibi connect-servers --server <user@host>` once for your servers. It creates a GitHub App that can only read your application repository and puts it on each server, so every install and every Software › Releases check gets a new read-only token, and nobody has to make a token again. [Connecting servers](connecting-servers.md) explains each step. If verification fails, download the asset from the release again or inspect the failed **Release setup** run. Do not bypass the check or rebuild on the server.

## Where to go next

[Settings](settings.md) explains each instance’s configuration. The Platform’s [server installation reference](https://github.com/BelimbingProject/bilibi/blob/main/docs/server-install.md) covers a fresh server and its [Software reference](https://github.com/BelimbingProject/bilibi/blob/main/apps/base/software/README.md) covers install and Undo.
