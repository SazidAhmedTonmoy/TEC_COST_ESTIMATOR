# Update an existing TEC ConEst installation to v2.3

## Recommended package: update-only

The update-only ZIP contains only new or changed application files. It excludes databases, backups, imports, exports, environments and local Git history. Use it for your existing v2.2 installation.

1. Ask other users to finish their work and stop the app/server. Make a separate backup copy of the entire current application folder, especially its live data/conest_catalog.db. With the server stopped, copy the full data folder, including any SQLite sidecar files. Keep this rollback copy outside the app's one-backup retention folder.
2. Extract TEC_ConEst_v2.3_Update_Only.zip. Open its inner folder and copy its CONTENTS into your existing app folder, where app.py already lives. Replace matching application files and merge the assets, conest_app and tests folders. Do not nest the update folder inside the app. Keep the existing data folder, .env, environment variables, .venv/venv, Git history, .htaccess and passenger_wsgi.py.
3. Start with START_TEC_SERVER.bat on Windows or sh run.sh on Linux/macOS. The launchers now check the image dependency as well as the existing Excel/PDF dependencies. Where you manage Python yourself, install requirements.txt into the SAME Python environment used by the server before restarting.
4. On startup, the app automatically adds the v2.3 schema to the existing main database. Do not start multiple old/new app processes against the database during the upgrade.
5. Open the app and hard-refresh the browser (Ctrl+F5). Confirm Estimator v2.3 in the sidebar. Check an existing estimate, a project reference in Excel, the calendar month and a light-price entry.

Manual dependency installation examples:

Windows, from the existing app folder:

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux/macOS:

```sh
.venv/bin/python -m pip install -r requirements.txt
```

Use the actual environment path when your server uses venv rather than .venv. Initial installation of a missing dependency requires an internet connection. The new dependency is Pillow for validating and storing photos.

## GitHub / existing cPanel workflow

Copy the update contents into your existing Git checkout, review, commit and push. Keep database files out of Git. The supplied deployment workflow retains its existing data exclusions, installs requirements and restarts Passenger. It is unchanged by this release. Preserve your existing hosting files and secrets. A ZIP release does not itself deploy the site.

## Full package

TEC_ConEst_WebApp_v2.3.zip contains the complete app plus the database snapshot from the uploaded v2.2 ZIP. That snapshot was left byte-for-byte unchanged during development and migrates on first startup. It may be older than your live database. Do not overwrite production data with it. For an existing installation, the update-only package is safer.

## Rollback

Stop v2.3 and restore BOTH the previous application code and its matching pre-upgrade database backup. Do not assume that simply putting v2.2 code over a database already edited by v2.3 is a complete rollback. Preserve any post-upgrade work separately before restoring an older database.

## Post-update checks

Confirm that the four-project chooser scrolls, Won/Lost can be cleared, refs stay project-only, and the expected reference appears in the same Excel item cell. On Light price check, verify a known multi-component quote before relying on its package price. Use Copy image, not Copy image address, when testing paste. Delete a disposable test account only, not a real working account, when checking the admin deletion control.
