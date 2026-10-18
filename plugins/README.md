# Vendored DSH plugins

DeepSeek Harness (DSH) loads npm-style packages into a *profile*. The Bridge's
headless Harness host uses the `web` profile, so anything that profile needs must
be installable on the machine that runs the robot.

These copies exist so a clean checkout does not depend on GitHub being reachable
or on a `pnpm` registry install. They are byte-for-byte copies of the published
package, including its prebuilt `lib/`, so nothing is compiled during install.

| Package | Version | Upstream | License | Used by |
|---|---|---|---|---|
| `dsh-plugin-session-delete` | 0.3.4 | [SereinHK/dsh-plugin-session-delete](https://github.com/SereinHK/dsh-plugin-session-delete) | MIT | `bridge/app/harness.py` permanent conversation deletion |

## Why this one is required

DSH deliberately has no native `session/delete`; archiving is the supported
non-destructive path. The Bridge offers real deletion in the web UI, which calls
`POST /api/session.delete` and then `POST /api/session.purge` on the Host. Those
routes are registered by this plugin. Without it the Host answers 404 and the
Bridge reports "永久删除扩展尚未加载" instead of archiving anything.

## Install

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_dsh_plugin.ps1
```

The installer copies the package into `%USERPROFILE%\.dsh\profiles\web\node_modules`,
rewrites that profile's dependency to a local `file:` path, and appends the plugin
to `dsh.profile.bundles`. It backs up `package.json` first and is idempotent.
Use `-ProfileName desktop` only if you also want the desktop profile to expose the
delete action. Restart the Bridge afterwards.

## Updating

1. Install the newer release upstream once (network required).
2. Copy the package contents over `plugins/dsh-plugin-session-delete/` and bump
   the version in this table.
3. Run the installer with `-Force`.
4. Run `python -m pytest bridge/tests -q`; `test_plugin_bundle.py` checks the
   vendored manifest, prebuilt files, routes and license.

Do not add model weights, credentials, or machine-specific absolute paths here.
