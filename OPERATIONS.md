# Runtime, load checks and monitoring

## One-host deployment

TEC Flow retains its compatible SQLite/WAL design. Reads can overlap writes;
each database still has one writer. Keep the application and both database
files on the same host's local disk. Increasing Python workers increases total
memory and database contention, so start with a small worker count and measure
on the actual hosting plan.

The WSGI adapter admits at most 4 active requests per worker, with at most 64
waiting requests and a 5-second admission timeout. Excess work receives
HTTP 503 with `Retry-After: 2`; running writes are allowed to finish. The standalone
server also bounds its connection threads. Its existing socket timeout remains
in effect; the reverse proxy/Passenger must enforce its own connection and body
read timeouts.

Request bodies over the existing 80 MiB upload ceiling are rejected before the
WSGI adapter reads them. Its concurrent input reservation is 128 MiB per worker.
This counts input bytes, not all Python memory: parsing, decoded uploads,
responses, caches and HTTP buffering need additional memory. Large uploads may
receive a retryable 503 while another upload is being processed. Standard
Content-Length uploads continue to work; decoded streams without a length are
read only if the WSGI server marks them as safely terminated.

| Environment setting | Default | Allowed range |
| --- | ---: | ---: |
| `CONEST_MAX_ACTIVE_REQUESTS` | 4 | 1–128 |
| `CONEST_MAX_QUEUED_REQUESTS` | 64 | 0–1024 |
| `CONEST_REQUEST_QUEUE_TIMEOUT_SECONDS` | 5 | 0.01–30 |
| `CONEST_MAX_BUFFERED_BODY_MIB` | 128 | 80–512 |

Invalid settings use the defaults. Restart workers after changing settings.
Tune these values from measurements; larger queues do not create more database
write capacity. Avoid automatically retrying a write whose response was lost:
check its outcome first. Revision checks protect concurrent edits from silent
overwrites.

## Storage, encryption keys and recovery

Saved Gemini credentials and all newly created database backup/recovery snapshots
use authenticated **AES-256-GCM** encryption. Backup downloads use `.db.enc`;
the browser receives the encrypted file. Authentication rejects altered files
and wrong keys before a recovered database is used. Existing saved plaintext
Gemini keys are encrypted during startup, and keys are never returned to the
Settings form.

The active databases remain ordinary SQLite files. Full protection of active
business data at rest requires encrypted hosting storage. Keys, new encrypted
backups and temporary restore/snapshot files are owner-only; live database file
ownership and permissions remain the host administrator's responsibility. Use
the same service account for Passenger and cron, private data-only directories
(`0700`), and owner-only database files and SQLite sidecars (`0600`). Prefer data
outside the public web directory and apply the supplied Apache protection rules
when retaining existing paths. Do not apply private-directory permissions to
the public static-assets directory. Authorized Excel/JSON exports are readable
files and need their own appropriate storage.

### Keep the original key

On first use, the app generates a random key outside the website under the
service account's `~/.tec-flow/keys/<catalog-path-hash>.key`. The key file uses
permissions `0600` and its directories use `0700`. **Keep a secure recovery copy
of this key separately from the encrypted backups.** Keys are not included in
downloads or release ZIPs. The database and a private sidecar record its
fingerprint; losing or changing the key causes protection operations to fail,
without falling back to plaintext or silently generating a replacement.

Operators may instead configure one of these settings:

| Setting | Required value |
| --- | --- |
| `CONEST_ENCRYPTION_KEY_FILE` | Absolute path outside the website to the original key file, owned by the service account with permissions `0600`. The file must already exist. |
| `CONEST_ENCRYPTION_KEY` | The same base64-encoded 32-byte key, supplied through a protected server environment. |

Do not configure both. Do not delete fingerprints or change the encryption key
to resolve a missing-key error; recover the original key. When changing the
catalog database path, service account or server, explicitly configure the
original key because the automatic key location depends on the catalog path
and service home. Run maintenance tools with the same catalog path and key
configuration as the website. After the app has initialized, this command
reports the key location/source and its non-secret fingerprint, without printing
the key:

```sh
python tools/protect_data.py status
```

The backup runtime configuration records a key-file path for cron, never key
contents. If using an environment-only key, supply that same secret to the cron
environment as well; cron fails if it is unavailable. Restart all application
workers after deployment or configuration changes.

### Retention and older files

The existing regular-backup policy keeps **one newest snapshot per database**.
Both `.db` and `.db.enc` files participate: creating or listing backups removes
older regular snapshots and their metadata. Keep additional recovery copies
outside those regular backup folders. Migration/recovery snapshots use separate
locations; existing plaintext originals there are not automatically encrypted
or removed by this update. The copy-only utility can encrypt a legacy snapshot
without modifying its source:

```sh
python tools/protect_data.py encrypt --source /private/legacy.db --output /private/legacy.db.enc --kind catalog
```

Retain or remove the original plaintext copy according to your recovery needs
after verifying the encrypted copy. Downloads created before this release and
other exported files are not retroactively protected.

### Verify or recover an encrypted backup

Configure the original key first. These commands create a new private recovery
copy and refuse to overwrite any existing output:

```sh
python tools/protect_data.py verify --source /private/backup.db.enc --kind catalog
python tools/protect_data.py decrypt --source /private/backup.db.enc --output /private/recovered.db --kind catalog
```

Use `--kind tenders` for Tender snapshots. Verification checks both encryption
authentication and SQLite integrity. The decrypted copy is readable SQLite;
keep it private. The utility does not install it as the live database.

The application's Estimator restore control checks schema compatibility,
creates an encrypted safety backup, restores in place and signs everyone out.
For an administrator-managed Tender restore, stop all application and cron
writers first. Preserve the current database and any `-wal`/`-shm` companions
together in a private recovery location, install the verified recovery copy at
the configured path with the correct ownership, then restart and validate
`/api/health?check=tenders`. Do not replace a database while workers still have
it open.

### Session expiry

Sessions have an absolute **12-hour** lifetime by default; activity or page
refreshes do not extend it. `CONEST_SESSION_HOURS` accepts an integer from
1 to 720 and takes effect after a worker restart. New sessions receive the
configured expiry; legacy sessions without an expiry are checked against their
creation time. Accounts retaining a starter password must change it before
normal access.

## Repeatable offline load check

Run from the application folder using completed backups:

```sh
python tools/load_test.py --catalog-db /private/catalog-backup.db --tenders-db /private/tenders-backup.db --users 10,25,50 --iterations 10 --p95-ms 2000 --output /private/load-results.json
```

The tool has no live-host or URL mode. It copies both backups into a disposable
directory, creates synthetic users and revocable sessions, generates an
ephemeral encryption key, and performs authenticated requests through the real
WSGI adapter. Original backup hashes are checked afterward. Do not use an
actively written database file; take a consistent backup first. The supplied
legacy backups are suitable. For a newer database that already contains
encrypted settings, configure its original `CONEST_ENCRYPTION_KEY_FILE` or
`CONEST_ENCRYPTION_KEY` and add `--use-configured-key`. An encrypted `.db.enc`
backup must first be decrypted to an isolated recovery copy with
`tools/protect_data.py`; the harness still copies that recovery file before use.

Each round per simulated user contains six reads and two writes: Tender data,
Opportunity list/deadline warning, catalog search, notifications, Estimator
read/quantity edits with recalculation, and Opportunity edit. Each synthetic
estimate contains one catalog line with real copied component allowances.
The default run uses 10, 25 and 50 users with 10
rounds each: 6,800 measured requests and 1,700 writes. Setup and warm-up are not
included in latency results. The pass gates are zero unexpected responses,
verified write values and revisions, unchanged inputs, both database integrity
and foreign-key checks, correct monitoring access, bounded admission, and p95
latency at or below 2,000 ms at every level. The report also includes p99 and
throughput. The command exits nonzero when a gate fails.

This is one-worker, in-process WSGI testing. It does not measure network/TLS,
Passenger/reverse-proxy configuration, browser rendering, password-hash/login
load, large imports or estimates, catalog mutations, external AI services,
cold migration, or multi-host capacity. Repeat an authorized staging test on the real hosting resources
before making a production capacity claim. The tool's generated passwords,
tokens, key, private records and copied databases are not included in reports.

### v3.8.6 local validation

The supplied database copies contained 408 Tender submissions, 405 chase-ups,
167 Opportunities, 41 Estimator projects, 4,029 catalog items and 2,197 estimate
lines before synthetic test records were added. The final one-worker WSGI run
used Python 3.12.14 and SQLite 3.53.1 with the default 4 active request slots.

| Simulated users | Requests | p95 latency | p99 latency | Requests/second | Unexpected responses |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 800 | 246 ms | 338 ms | 80.82 | 0 |
| 25 | 2,000 | 576 ms | 898 ms | 90.72 | 0 |
| 50 | 4,000 | 1,534 ms | 1,979 ms | 75.14 | 0 |

All 1,700 writes were verified, both databases passed integrity and foreign-key
checks, and the original files were unchanged. Peak active work was 4 and peak
waiting work was 46; no requests were rejected. Administrator access and the
monitoring thresholds passed. These are local measurements under the stated
workload, not a benchmark of the live hosting account.

## Monitoring

`GET /api/health` remains the lightweight availability check.
`GET /api/health?check=tenders` additionally checks Tender readiness and a short
write probe; use it after deployment or diagnosis, not as a high-frequency
poll. The existing `tools/check_deployment_health.py` validates its JSON.

An administrator can open `GET /api/admin/runtime-metrics` while signed in.
Uncredentialed requests receive 401 and non-admin requests 403. The response is
not cacheable. It contains per-worker uptime, request/status counts, fixed route
categories, recent latency percentiles, rejection counts, queue occupancy and
buffer reservation. It contains no request bodies, cookies, usernames, project
IDs, share tokens, query strings, API keys or error messages.

Counters reset on worker restart. Latency percentiles cover the latest 2,048
completed requests. Each Passenger worker reports only its own counters;
polling behind a worker pool does not produce combined application metrics.
The monitoring request itself finishes after its snapshot is collected.

For a saved administrator metrics response:

```sh
python tools/check_runtime_metrics.py < /private/runtime-metrics.json
```

Exit 0 is healthy, exit 1 reports threshold alerts, and exit 2 indicates invalid
input. Defaults flag recent p95 above 2,000 ms, more than 1% server errors since
the worker started (after 20 samples), or a queue at least 80% full. Tune these
thresholds to the site's service target. Use a protected external uptime and
alerting service for production notifications; these tools do not install or
configure that service automatically.

If write contention or database size outgrows one host, move to a managed SQL
database with transaction-safe adapters and migrations, move expensive imports
to a bounded job queue, and add central metrics. That is a planned migration,
not a claim that the existing SQLite application supports unlimited users.
