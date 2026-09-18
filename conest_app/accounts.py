"""Database-backed accounts; salted scrypt hashes and revocable sessions."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time

from .utils import utc_now

# A one-time starter credential, stored only as a hash. Never reset an existing account.
from .initial_roster import INITIAL_ROSTER
STARTER_HASH = next(entry[2] for entry in INITIAL_ROSTER if entry[0]=='Tonmoy')
SESSION_SECONDS = 400 * 24 * 60 * 60
PUBLIC_FIELDS = ('id', 'username', 'name', 'job_title', 'role', 'is_active', 'must_change_password', 'created_at', 'updated_at', 'last_login_at')


class AccessError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def password_hash(password):
    if not isinstance(password, str) or not 8 <= len(password) <= 256:
        raise ValueError('Password must contain 8 to 256 characters')
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=3, maxmem=67108864)
    return f'scrypt$32768$8$3${salt.hex()}${value.hex()}'


def verify_password(password, encoded):
    if not isinstance(password, str) or len(password) > 256:
        return False
    try:
        algorithm, n, r, p, salt, expected = encoded.split('$')
        if algorithm != 'scrypt':
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), maxmem=67108864)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def public_user(row):
    result={key: row[key] for key in PUBLIC_FIELDS}
    for key in ('team_id','team_name','email','contact_number','avatar_version','has_avatar'):
        if key in row.keys():result[key]=row[key]
    return result


def initialize_accounts(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL COLLATE NOCASE UNIQUE,
            name TEXT NOT NULL, job_title TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','user')),
            is_active INTEGER NOT NULL DEFAULT 1,
            must_change_password INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_login_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE TABLE IF NOT EXISTS login_attempts (
            attempt_key TEXT PRIMARY KEY, failures INTEGER NOT NULL, window_start INTEGER NOT NULL
        );
    ''')
    # First initialization is serialized so concurrent startup cannot create two admins.
    conn.execute('BEGIN IMMEDIATE')
    if not conn.execute('SELECT 1 FROM users LIMIT 1').fetchone():
        encoded = STARTER_HASH
        now = utc_now()
        conn.execute('''INSERT INTO users(username,name,job_title,password_hash,role,created_at,updated_at)
                        VALUES ('Tonmoy','Tonmoy','Administrator',?,'admin',?,?)''', (encoded, now, now))
    conn.commit()


def validate_identity(payload, current=None):
    data = dict(current or {})
    data.update(payload)
    username = str(data.get('username', '')).strip()
    name = str(data.get('name', '')).strip()
    job_title = str(data.get('job_title', '')).strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}', username):
        raise ValueError('Username must be 3–64 letters, numbers, dots, hyphens or underscores')
    if not 1 <= len(name) <= 120 or len(job_title) > 120:
        raise ValueError('Enter a name and keep name and job title within 120 characters')
    return username, name, job_title



def validate_contact(value):
    if not isinstance(value, str):
        raise ValueError('Contact number must be text')
    value = value.strip()
    if len(value) > 50 or (value and (not re.fullmatch(r'[0-9+(). #xXeEtT/-]+', value) or not re.search(r'\d', value))):
        raise ValueError('Enter a contact number of up to 50 characters, including a country code or extension, or leave it blank')
    return value


def validate_email(value):
    value = str(value or '').strip()
    if value and (len(value) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value)):
        raise ValueError('Enter a valid email address or leave Email blank')
    return value

def create_user(conn, payload):
    from .teams import validate_team
    username, name, job_title = validate_identity(payload)
    role = payload.get('role', 'user')
    if role not in ('admin', 'user'):
        raise ValueError('Choose admin or user')
    team_id=validate_team(conn,role,payload.get('team_id'))
    contact = validate_contact(payload.get('contact_number', ''))
    email = validate_email(payload.get('email', ''))
    encoded = password_hash(payload.get('password'))
    now = utc_now()
    cursor = conn.execute('''INSERT INTO users(username,name,job_title,password_hash,role,created_at,updated_at)
                             VALUES (?,?,?,?,?,?,?)''', (username, name, job_title, encoded, role, now, now))
    conn.execute('UPDATE users SET team_id=?,contact_number=?,email=? WHERE id=?',(team_id,contact,email,cursor.lastrowid))
    return public_user(conn.execute('SELECT * FROM users WHERE id=?', (cursor.lastrowid,)).fetchone())


def edit_user(conn, target_id, payload, actor, admin=False):
    from .teams import validate_team
    current = conn.execute('SELECT * FROM users WHERE id=?', (target_id,)).fetchone()
    if not current:
        raise LookupError('User not found')
    if not admin and (target_id != actor['id'] or any(k in payload for k in ('role', 'is_active', 'must_change_password','team_id'))):
        raise AccessError(403, 'You can only edit your own profile')
    username, name, title = validate_identity(payload, current)
    email = validate_email(payload.get('email', current['email']))
    contact = validate_contact(payload.get('contact_number', current['contact_number']))
    if type(payload.get('remove_photo', False)) is not bool:
        raise ValueError('Invalid Remove photo selection')
    if payload.get('photo_data_url') and payload.get('remove_photo'):
        raise ValueError('Choose a new photo or remove the current photo, not both')
    photo = None
    if payload.get('photo_data_url'):
        from .images import prepare_image
        photo = prepare_image(payload['photo_data_url'], max_side=512, max_mb=8, square=True)
    password = payload.get('password')
    if not admin and (password or username != current['username']):
        if not verify_password(payload.get('current_password'), current['password_hash']):
            raise ValueError('Current password is incorrect')
    if not admin and current['must_change_password'] and not password:
        raise ValueError('Choose a new password to finish setting up your account')
    if not admin and password and verify_password(password, current['password_hash']):
        raise ValueError('Choose a password different from your current password')
    role = payload.get('role', current['role']) if admin else current['role']
    active = payload.get('is_active', current['is_active']) if admin else current['is_active']
    if role not in ('admin', 'user') or active not in (0, 1, False, True):
        raise ValueError('Invalid role or account status')
    team_id=validate_team(conn,role,payload.get('team_id',current['team_id']))
    if current['role'] == 'admin' and current['is_active'] and (role != 'admin' or not active):
        if conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0] <= 1:
            raise ValueError('At least one active administrator must remain')
    encoded = password_hash(password) if password else current['password_hash']
    must_change = (1 if admin else 0) if password else current['must_change_password']
    conn.execute('''UPDATE users SET username=?,name=?,job_title=?,password_hash=?,role=?,is_active=?,
                    must_change_password=?,updated_at=? WHERE id=?''',
                 (username, name, title, encoded, role, int(active), must_change, utc_now(), target_id))
    if password or role != current['role'] or active != current['is_active'] or username != current['username']:
        conn.execute('DELETE FROM sessions WHERE user_id=?', (target_id,))
    conn.execute('UPDATE users SET team_id=?,email=?,contact_number=? WHERE id=?',(team_id,email,contact,target_id))
    if photo or payload.get('remove_photo'):
        _replace_profile_photo(conn, target_id, photo)
    return public_user(conn.execute('SELECT * FROM users WHERE id=?', (target_id,)).fetchone())


def _replace_profile_photo(conn, user_id, photo):
    """Keep just the new avatar in the live database, with rollback on failure.

    secure_delete clears removed table content; historical backups/journals
    are outside this operation. Do not VACUUM or delete backup files on upload.
    """
    previous = int(conn.execute('PRAGMA secure_delete').fetchone()[0])
    conn.execute('PRAGMA secure_delete=ON')
    conn.execute('SAVEPOINT replace_profile_photo')
    try:
        conn.execute('DELETE FROM user_avatars WHERE user_id=?', (user_id,))
        if photo:
            conn.execute('INSERT INTO user_avatars(user_id,mime,image,updated_at) VALUES (?,?,?,?)',
                         (user_id, *photo, utc_now()))
        conn.execute('UPDATE users SET avatar_version=avatar_version+1,has_avatar=? WHERE id=?',
                     (int(bool(photo)), user_id))
        conn.execute('RELEASE replace_profile_photo')
    except Exception:
        conn.execute('ROLLBACK TO replace_profile_photo')
        conn.execute('RELEASE replace_profile_photo')
        raise
    finally:
        # The value came from SQLite, never from a request.
        conn.execute('PRAGMA secure_delete=' + str(previous))


def start_session(conn, user_id):
    token = secrets.token_urlsafe(48)
    now = int(time.time())
    conn.execute('DELETE FROM sessions WHERE expires_at>0 AND expires_at<=?', (now,))
    conn.execute('INSERT INTO sessions VALUES (?,?,?,?)', (token_digest(token), user_id, 0, utc_now()))
    return token


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token):
    return hashlib.sha256(('conest-csrf:' + token).encode()).hexdigest()


def session_user(conn, token):
    if not token or len(token) > 256:
        return None
    row = conn.execute('''SELECT u.*,t.name AS team_name FROM sessions s JOIN users u ON u.id=s.user_id
                          LEFT JOIN teams t ON t.id=u.team_id
                          WHERE s.token_hash=? AND (s.expires_at=0 OR s.expires_at>?) AND u.is_active=1''',
                       (token_digest(token), int(time.time()))).fetchone()
    return public_user(row) if row else None


def login(conn, payload, address):
    username = str(payload.get('username', '')).strip()[:64]
    now = int(time.time())
    keys = [token_digest('user:' + username.casefold()), token_digest('address:' + address)]
    conn.execute('DELETE FROM login_attempts WHERE window_start<?', (now - 900,))
    for key, limit in zip(keys, (10, 50)):
        row = conn.execute('SELECT * FROM login_attempts WHERE attempt_key=?', (key,)).fetchone()
        if row and row['failures'] >= limit:
            raise AccessError(429, 'Too many sign-in attempts. Try again in 15 minutes.')
    row = conn.execute('SELECT * FROM users WHERE username=? COLLATE NOCASE', (username,)).fetchone()
    valid = verify_password(payload.get('password'), row['password_hash'] if row else STARTER_HASH)
    if not row or not valid or not row['is_active']:
        for key in keys:
            conn.execute('''INSERT INTO login_attempts VALUES (?,1,?)
                            ON CONFLICT(attempt_key) DO UPDATE SET failures=failures+1''', (key, now))
        conn.commit()  # Preserve throttling after the caller returns a sign-in error.
        raise AccessError(401, 'Incorrect username or password')
    conn.execute('DELETE FROM login_attempts WHERE attempt_key=?', (keys[0],))
    conn.execute('UPDATE users SET last_login_at=? WHERE id=?', (utc_now(), row['id']))
    token = start_session(conn, row['id'])
    return public_user(conn.execute('SELECT * FROM users WHERE id=?', (row['id'],)).fetchone()), token
