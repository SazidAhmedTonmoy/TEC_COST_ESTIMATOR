#Main Code

from __future__ import annotations

import argparse
import time
import sys
import json
import mimetypes
import os
import re
import sqlite3
import socket
import uuid
import tempfile
import threading
import traceback
import webbrowser
from zipfile import BadZipFile
from openpyxl.utils.exceptions import InvalidFileException
from email.parser import BytesParser
from email.policy import default as email_policy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from conest_app.assistant import (
    DEFAULT_GEMINI_MODEL,
    FREE_TIER_GEMINI_MODELS,
    gemini_key_configured,
    interpret_request,
    test_gemini_connection,
)
from conest_app.catalog import (
    catalog_overview,
    create_manual_catalog_item,
    get_catalog_item,
    list_import_issues,
    list_sources,
    search_catalog,
    update_manual_catalog_item,
)
from conest_app.database import write_lock, connect, database_path, get_settings, initialize, update_settings
from conest_app.exporter import default_export_name, export_project
from conest_app.importer import import_workbook
from conest_app.projects import (
    add_catalog_line,
    calculate_project,
    create_project,
    delete_project_line,
    delete_project,
    list_projects,
    save_manual_estimate_item,
    update_project,
    update_project_line,
)
from conest_app.taxonomy import CATALOG_CATEGORIES, WORK_TYPES
from conest_app.utils import clean_text, safe_filename, utc_now
from conest_app.http_workspace import WorkspaceHTTP
from conest_app.http_productivity import ProductivityHTTP
from conest_app.productivity import capture_price
from conest_app import accounts, backups, import_preview
from conest_app.accounts import AccessError
from conest_app.workspace import update_workflow, register_project, visible_projects, check_revision, get_project


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
IMPORT_DIR = ROOT / "data" / "imports"
EXPORT_DIR = ROOT / "data" / "exports"
MAX_UPLOAD_BYTES = 80 * 1024 * 1024
IMPORT_SLOTS = threading.BoundedSemaphore(2)


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


class ConEstHandler(ProductivityHTTP, WorkspaceHTTP, BaseHTTPRequestHandler):
    server_version = "TECConEst/3.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(120)

    def parse_request(self):
        valid=super().parse_request()
        self._request_started=time.perf_counter()
        return valid

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def _security_headers(self) -> None:
        started=getattr(self,'_request_started',None)
        if started is not None:
            elapsed=(time.perf_counter()-started)*1000
            self.send_header('Server-Timing',f'request;dur={elapsed:.1f}')
            if elapsed>=2000 and self.path.startswith('/api/'):
                print(f'ConEst slow request pid={os.getpid()} {self.command} {urlparse(self.path).path} {elapsed:.0f}ms',file=sys.stderr,flush=True)
        if self.response_cookie:
            self.send_header('Set-Cookie', self.response_cookie)
            self.response_cookie = None
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'" + (" 'unsafe-inline'" if self.path.startswith("/tenders") else "") + "; script-src 'self'; connect-src 'self'",
        )

    def _send_json(self, payload: object, status: int = 200) -> None:
        payload = self._public_payload(payload)
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, download_name: str | None = None) -> None:
        if not path.is_file():
            raise ApiError(404, "File not found")
        body = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        if download_name:
            self.send_header('Cache-Control', 'no-store')
            quoted = quote(download_name)
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted}")
        else:
            # Only versioned public assets are cached; HTML and exports stay fresh.
            versioned_asset = path.parent == ASSETS and path.suffix != '.html' and ('v=2.4' in self.path or re.fullmatch(r'(?:app|styles|theme)\.[a-f0-9]{12}\.(?:js|css)', path.name))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable" if versioned_asset else "no-cache")
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(400, "Invalid Content-Length") from exc
        if length <= 0:
            return {}
        if length > MAX_UPLOAD_BYTES:
            raise ApiError(413, "Request is too large")
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(400, "Invalid JSON body") from exc
        if not isinstance(value, dict):
            raise ApiError(400, "JSON body must be an object")
        return value

    def _multipart_file(self, field_name: str = "file") -> tuple[str, bytes]:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type.lower():
            raise ApiError(400, "Expected multipart/form-data")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(400, "Invalid Content-Length") from exc
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            raise ApiError(413 if length > MAX_UPLOAD_BYTES else 400, "Invalid upload size")
        raw = self.rfile.read(length)
        message = BytesParser(policy=email_policy).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + raw
        )
        for part in message.iter_parts():
            if part.get_param("name", header="content-disposition") != field_name:
                continue
            filename = part.get_filename() or "upload.xlsx"
            return safe_filename(filename), part.get_payload(decode=True) or b""
        raise ApiError(400, f"Missing upload field '{field_name}'")

    def _route(self) -> tuple[str, dict[str, list[str]]]:
        parsed = urlparse(self.path)
        return parsed.path, parse_qs(parsed.query)

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, (ApiError, AccessError)):
            self._send_json({"success": False, "error": exc.message}, exc.status)
            return
        if isinstance(exc, LookupError):
            self._send_json({"success": False, "error": str(exc)}, 404)
            return
        if isinstance(exc, (ValueError, sqlite3.IntegrityError)):
            self._send_json({"success": False, "error": str(exc)}, 400)
            return
        if isinstance(exc, sqlite3.OperationalError) and ("locked" in str(exc) or "busy" in str(exc)):
            self._send_json({"success": False, "error": "The database is busy. Please retry shortly."}, 503)
            return
        from conest_app.auto_upgrade import UpgradeError
        from conest_app.quotation_parser import ImportDependencyError
        if isinstance(exc, (UpgradeError, ImportDependencyError)):
            self._send_json({"success": False, "error": str(exc)}, 503)
            return
        reference = uuid.uuid4().hex[:12]
        print(f"TEC ConEst server error reference: {reference}", flush=True)
        traceback.print_exc()
        self._send_json({"success": False, "error": f"The server could not complete this request. Error reference: {reference}. Ask your administrator to check the server log.", "error_reference": reference}, 500)

    def _tender_route(self, path):
        if not (path == '/tenders' or path.startswith('/tenders/') or path.startswith('/api/tenders/')):
            return False
        from conest_app.tender_http import route
        route(self,path)
        return True

    def _dashboard_payload(self):
        with self._read_connection() as conn:
            catalog = catalog_overview(conn)
            counts = {
                "catalog_items": catalog["usable_catalog_groups"],
                "catalog_groups": catalog["catalog_groups"],
                "source_variants": catalog["source_variants"],
                "reference_only_variants": catalog["reference_only_variants"],
                "components": conn.execute("SELECT COUNT(*) FROM catalog_components").fetchone()[0],
                "source_files": conn.execute("SELECT COUNT(DISTINCT file_sha256) FROM sources").fetchone()[0],
                "source_sheets": conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
                "projects": conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
                "review_issues": conn.execute("SELECT COUNT(*) FROM import_issues WHERE resolved=0").fetchone()[0],
            }
            projects = visible_projects(conn, self.user)
            sources = list_sources(conn)[:8]
            categories = list(dict.fromkeys([*CATALOG_CATEGORIES,
                *(row[0] for row in conn.execute("SELECT DISTINCT category FROM catalog_items WHERE is_active=1 ORDER BY category")),
                *(row[0] for row in conn.execute("SELECT DISTINCT category_snapshot FROM project_lines ORDER BY category_snapshot") if row[0])]))
        return {"success": True, "counts": counts, "catalog": catalog, "projects": projects, "sources": sources,
                         "manual_options": {"categories": categories, "work_types": WORK_TYPES}}

    def _settings_payload(self):
        with self._read_connection() as conn:
            settings = get_settings(conn)
            configured = gemini_key_configured(conn)
            stored = conn.execute("SELECT value FROM settings WHERE key='gemini_api_key'").fetchone()
        settings["llm_provider"] = "gemini"
        settings["llm_model"] = settings.get("llm_model") or DEFAULT_GEMINI_MODEL
        settings["llm_api_key_configured"] = configured
        settings["llm_api_key_source"] = (
            "saved" if stored and stored[0].strip()
            else "environment" if os.environ.get("GEMINI_API_KEY", "").strip()
            else "none"
        )
        settings["llm_models"] = list(FREE_TIER_GEMINI_MODELS)
        settings["llm_free_tier_only"] = True
        return {"success": True, "settings": settings}

    def do_GET(self) -> None:  # noqa: N802
        try:
            path, query = self._route()
            if path == '/api/bootstrap':
                self._guard('/api/auth/session')
                payload={'success':True,'user':self.user,'csrf_token':accounts.csrf_token(self.session_token)}
                if not self.user['must_change_password']:
                    payload['settings']=self._settings_payload()['settings']
                    payload['dashboard']=self._dashboard_payload()
                from conest_app.tender_http import send
                send(self,self._public_payload(payload));return
            if self._tender_route(path):return
            if self._productivity_route(path) or self._workspace_route(path):
                return
            self._guard(path)
            if path == "/":
                self._send_file(ASSETS / "index.html")
                return
            if path.startswith("/assets/"):
                relative = Path(path.removeprefix("/assets/"))
                if relative.name != str(relative) or relative.name.startswith("."):
                    raise ApiError(404, "Asset not found")
                self._send_file(ASSETS / relative)
                return
            if path == "/api/health":
                with connect() as conn:
                    schema = conn.execute('SELECT version FROM schema_version').fetchone()[0]
                self._send_json({"success": True, "status": "ok", "schema_version": schema, "release": "3.1"})
                return
            if path == '/api/light-prices':
                from conest_app import light_prices
                self._send_json({'success':True,**light_prices.search(query.get('q',[''])[0],offset=query.get('offset',[0])[0],supplier=query.get('supplier',[]))});return
            if path == '/api/light-prices/backup':
                from conest_app import light_prices
                if self.user['role']!='admin':raise ApiError(403,'Administrator access is required')
                with tempfile.TemporaryDirectory() as folder:
                    output=Path(folder)/'conest_catalog.db'
                    with light_prices.connect() as source:
                        with sqlite3.connect(output) as target:source.backup(target)
                    self._send_file(output,'conest_catalog.db')
                return
            photo_match=re.fullmatch(r'/api/light-prices/(\d+)/photo',path)
            if photo_match:
                with self._read_connection() as conn:
                    photo=conn.execute('SELECT mime,image FROM lighting_photos WHERE group_id=?',(int(photo_match[1]),)).fetchone()
                if not photo:raise ApiError(404,'Light photo not found')
                body=bytes(photo['image'])
                self.send_response(200)
                self.send_header('Content-Type',photo['mime'])
                self.send_header('Content-Length',str(len(body)))
                self.send_header('Cache-Control','private, no-store')
                self._security_headers();self.end_headers();self.wfile.write(body)
                return
            light_match=re.fullmatch(r'/api/light-prices/(\d+)',path)
            if light_match:
                from conest_app import light_prices
                self._send_json({'success':True,'item':light_prices.detail(int(light_match[1]))});return
            if path == '/api/import-history':
                from conest_app.import_history import list_uploads
                with self._read_connection() as conn:
                    result = list_uploads(conn, self.user, query)
                self._send_json({'success': True, **result})
                return
            if path == "/api/dashboard":
                self._send_json(self._dashboard_payload());return
            if path == "/api/catalog/search":
                term = query.get("q", [""])[0]
                limit = int(query.get("limit", ["20"])[0])
                category = query.get("category", [""])[0]
                include_incomplete = query.get("include_incomplete", ["0"])[0].lower() in {"1", "true", "yes"}
                group_variants = query.get("group_variants", ["1"])[0].lower() not in {"0", "false", "no"}
                with self._read_connection() as conn:
                    results = search_catalog(
                        conn,
                        term,
                        limit,
                        category=category,
                        include_incomplete=include_incomplete,
                        group_variants=group_variants,
                        recent_first=query.get("recent_first", ["0"])[0] == "1",
                    )
                self._send_json({"success": True, "query": term, "results": results})
                return
            match = re.fullmatch(r"/api/catalog/(\d+)", path)
            if match:
                with self._read_connection() as conn:
                    item = get_catalog_item(conn, int(match.group(1)))
                if not item:
                    raise ApiError(404, "Catalog item not found")
                self._send_json({"success": True, "item": item})
                return
            if path == "/api/projects":
                with self._read_connection() as conn:
                    projects = visible_projects(conn, self.user)
                self._send_json({"success": True, "projects": projects})
                return
            match = re.fullmatch(r"/api/projects/(\d+)", path)
            if match:
                with self._read_connection() as conn:
                    project = self._project_payload(conn, calculate_project(conn, int(match.group(1))))
                self._send_json({"success": True, **project})
                return
            match = re.fullmatch(r"/api/projects/(\d+)/export", path)
            if match:
                project_id = int(match.group(1))
                with self._read_connection() as conn:
                    project = calculate_project(conn, project_id, include_components=False)["project"]
                    name = default_export_name(project["name"])
                    with tempfile.TemporaryDirectory(prefix='conest-export-') as directory:
                        target = Path(directory) / name
                        export_project(conn, project_id, target)
                        self._send_file(target, name)
                return
            if path == "/api/imports":
                with self._read_connection() as conn:
                    items = list_sources(conn)
                self._send_json({"success": True, "sources": items})
                return
            if path == "/api/import-issues":
                unresolved = query.get("unresolved", ["0"])[0] in {"1", "true"}
                with self._read_connection() as conn:
                    issues = list_import_issues(conn, unresolved)
                self._send_json({"success": True, "issues": issues})
                return
            if path == "/api/settings/saved-key":
                # Requested explicitly by the Settings form; normal settings
                # responses and the dashboard continue to omit credentials.
                with self._read_connection() as conn:
                    saved = get_settings(conn, include_secrets=True).get("gemini_api_key", "")
                self._send_json({"success": True, "api_key": saved})
                return
            if path == "/api/settings":
                self._send_json(self._settings_payload());return
            raise ApiError(404, "Route not found")
        except Exception as exc:
            self._handle_error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            path, _ = self._route()
            if self._tender_route(path):return
            if self._productivity_route(path) or self._workspace_route(path):
                return
            self._guard(path)
            if path == '/api/light-prices/preview':
                from conest_app import lighting_imports
                if not IMPORT_SLOTS.acquire(blocking=False):
                    raise ApiError(429, 'Other quotation files are being checked. Please retry shortly.')
                try:
                    filename, content = self._multipart_file()
                    result = lighting_imports.create_preview(filename, content, self.user,
                        lambda conn: self._authorize_connection(conn, path))
                    self._send_json({'success': True, **result})
                finally:
                    IMPORT_SLOTS.release()
                return
            if path == '/api/light-prices/import':
                from conest_app import lighting_imports
                if 'multipart/form-data' in self.headers.get('Content-Type', '').lower():
                    raise ApiError(409, 'Quotation imports now require a review. Refresh this page, choose the file, and click Check quotation before importing.')
                payload = self._json_body()
                result = lighting_imports.commit_preview(payload.get('preview_id'), payload.get('selected'), self.user,
                    lambda conn: self._authorize_connection(conn, path))
                self._send_json({'success': True, **result})
                return
            tools_match=re.fullmatch(r'/api/projects/(\d+)/(copy|reorder|lines/(\d+)/(copy|components/reorder|components/(\d+)/copy))',path)
            if tools_match:
                from conest_app import estimate_tools
                payload=self._json_body();pid=int(tools_match[1]);lid=int(tools_match[3]) if tools_match[3] else None
                with self._write_connection() as conn:
                    if tools_match[2]=='copy':
                        pid=estimate_tools.copy_project(conn,pid,self.user,payload)
                    elif tools_match[2]=='reorder':
                        estimate_tools.reorder_lines(conn,pid,payload)
                        self._audit(conn,pid,'Reordered categories' if 'scope_order' in payload else 'Reordered estimate items')
                    elif tools_match[4]=='copy':
                        estimate_tools.copy_line(conn,pid,lid,payload)
                        name=conn.execute('SELECT name_snapshot FROM project_lines WHERE id=?',(lid,)).fetchone()[0]
                        self._audit(conn,pid,'Copied estimate item',name)
                    else:
                        action='copy' if tools_match[5] else 'reorder'
                        estimate_tools.component_action(conn,pid,lid,payload,action,int(tools_match[5]) if tools_match[5] else None)
                        name=conn.execute('SELECT name_snapshot FROM project_lines WHERE id=?',(lid,)).fetchone()[0]
                        self._audit(conn,pid,'Copied component' if action=='copy' else 'Reordered components',name)
                    if tools_match[2]=='reorder' and isinstance(payload.get('_known_lines'),dict):
                        result=self._project_payload(conn,{'project':dict(get_project(conn,pid))})
                        result.update(estimate_order=True,line_order=payload['ids'],line_versions=[dict(row) for row in conn.execute('SELECT id,revision,sort_order,updated_at FROM project_lines WHERE project_id=?',(pid,))])
                    else:
                        result=self._estimate_delta(self._project_payload(conn,calculate_project(conn,pid)),payload)
                    conn.commit()
                self._send_json({'success':True,**result},201)
                return
            manual_match = re.fullmatch(r"/api/projects/(\d+)/(?:manual-items|lines/(\d+)/manual-item)", path)
            if manual_match:
                payload = self._json_body()
                with self._write_connection() as conn:
                    result = save_manual_estimate_item(
                        conn, int(manual_match.group(1)), payload,
                        int(manual_match.group(2)) if manual_match.group(2) else None,
                    )
                    if result.get('catalog_saved'):capture_price(conn,result['item']['id'],self.user['id'],payload.get('item',{}),payload.get('item',{}).get('source_item_id'))
                    self._audit(conn, int(manual_match.group(1)), 'Saved manual estimate item', result['item']['name'])
                    result = self._estimate_delta(self._project_payload(conn, result),payload)
                    conn.commit()
                self._send_json({"success": True, **result}, 201)
                return
            if path == "/api/catalog":
                payload = self._json_body()
                with self._write_connection() as conn:
                    item = create_manual_catalog_item(conn, payload)
                    capture_price(conn,item['id'],self.user['id'],payload, payload.get('source_item_id'))
                    conn.commit()
                self._send_json({"success": True, "item": item}, 201)
                return
            if path == "/api/projects":
                payload = self._json_body()
                with self._write_connection() as conn:
                    project = create_project(conn, payload)
                    project_id = project['project']['id']
                    register_project(conn, project_id, self.user)
                    workflow = {key: payload[key] for key in ('scope_of_work', 'submission_deadline', 'status', 'team_ids', 'is_published', 'assignee_ids') if key in payload}
                    if workflow:
                        update_workflow(conn, project_id, workflow, self.user)
                    project = self._project_payload(conn, calculate_project(conn, project_id))
                    conn.commit()
                self._send_json({"success": True, **project}, 201)
                return
            match = re.fullmatch(r"/api/projects/(\d+)/lines", path)
            if match:
                payload = self._json_body()
                with self._write_connection() as conn:
                    result = add_catalog_line(
                        conn,
                        int(match.group(1)),
                        int(payload.get("catalog_item_id", 0)),
                        payload.get("quantity", 1),
                        clean_text(payload.get("query")),
                    )
                    self._audit(conn, int(match.group(1)), 'Added estimate item', f"Catalog item {payload.get('catalog_item_id')}, quantity {payload.get('quantity', 1)}")
                    result = self._estimate_delta(self._project_payload(conn, result),payload)
                    conn.commit()
                self._send_json({"success": True, **result}, 201)
                return
            if path == "/api/assistant/help":
                from conest_app.help_chat import prepare_context, answer_context
                payload=self._json_body()
                with self._read_connection() as conn:
                    prepared=prepare_context(conn,self.user,payload)
                self._send_json({"success":True,**answer_context(prepared)})
                return
            if path == "/api/assistant/interpret":
                payload = self._json_body()
                text = clean_text(payload.get("text"))
                if not text:
                    raise ValueError("text is required")
                with connect() as conn:
                    result = interpret_request(conn, text)
                self._send_json({"success": True, **result})
                return
            if path == "/api/settings/test-llm":
                payload = self._json_body()
                model = clean_text(payload.get("llm_model")) or None
                if model and model not in FREE_TIER_GEMINI_MODELS:
                    raise ValueError("Select a supported free-tier Gemini model")
                api_key = clean_text(payload.get("gemini_api_key")) or None
                with connect() as conn:
                    result = test_gemini_connection(conn, api_key=api_key, model=model)
                self._send_json({"success": result["success"], **result}, 200 if result["success"] else 400)
                return
            preview_commit=re.fullmatch(r'/api/import-previews/([a-f0-9]{32})/commit',path)
            if preview_commit:
                report=import_preview.commit_preview(preview_commit[1],self.user,self._json_body(),lambda conn:self._authorize_connection(conn,path))
                self._send_json({'success':True,'report':report},201)
                return
            if path in ("/api/imports", "/api/import-previews"):
                filename, content = self._multipart_file()
                if Path(filename).suffix.lower() not in {".xlsx", ".xlsm"}:
                    raise ValueError("Only .xlsx and .xlsm files are supported")
                if not content:
                    raise ValueError("Uploaded workbook is empty")
                IMPORT_DIR.mkdir(parents=True, exist_ok=True)
                timestamp = utc_now().replace(":", "").replace("+00:00", "Z")
                target = IMPORT_DIR / f"{timestamp}-{uuid.uuid4().hex[:12]}-{filename}"
                if not IMPORT_SLOTS.acquire(blocking=False):
                    raise ApiError(429, "Two workbooks are already processing. Please retry when an import finishes.")
                try:
                    target.write_bytes(content)
                    if path=='/api/import-previews':
                        report=import_preview.build_preview(target,filename,self.user,lambda conn:self._authorize_connection(conn,path))
                    else:
                        with write_lock:
                            with connect() as auth_conn:self._authorize_connection(auth_conn,path)
                            backups.create_backup('before-import',self.user['id'])
                            report = import_workbook(target, display_name=filename, initialize_database=False,
                                actor_id=self.user['id'], authorize=lambda conn: self._authorize_connection(conn, path))
                except (BadZipFile, InvalidFileException) as exc:
                    target.unlink(missing_ok=True)
                    raise ValueError("The upload is not a valid Excel workbook. Open it in Excel and save as .xlsx.") from exc
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
                finally:
                    IMPORT_SLOTS.release()
                self._send_json({"success": True, "report": report}, 201)
                return
            raise ApiError(404, "Route not found")
        except Exception as exc:
            self._handle_error(exc)

    def do_PATCH(self) -> None:  # noqa: N802
        try:
            path, _ = self._route()
            if self._tender_route(path):return
            if self._productivity_route(path) or self._workspace_route(path):
                return
            self._guard(path)
            payload = self._json_body()
            light_match = re.fullmatch(r'/api/light-prices/(\d+)', path)
            if light_match:
                from conest_app import light_prices
                with self._write_connection() as conn:
                    item=light_prices.update(conn,int(light_match[1]),payload,self.user)
                self._send_json({'success':True,'item':item})
                return
            match = re.fullmatch(r"/api/projects/(\d+)", path)
            if match:
                with self._write_connection() as conn:
                    # Builders belong to the project brief, managed by its owner/admin.
                    # A cached old form may still send the unchanged client field.
                    if 'builders' in payload or 'client' in payload:
                        from conest_app.builders import stored_builders, read_builders
                        from conest_app.workspace import require_project
                        current = get_project(conn, int(match.group(1)))
                        value = stored_builders(payload, current)
                        if read_builders({'client': value}) != read_builders(current):
                            require_project(conn, int(match.group(1)), self.user, 'manage')
                    project = update_project(conn, int(match.group(1)), payload)
                    self._audit(conn, int(match.group(1)), 'Updated estimate settings')
                    project = self._estimate_delta(self._project_payload(conn, project),payload)
                    conn.commit()
                self._send_json({"success": True, **project})
                return
            match = re.fullmatch(r"/api/projects/(\d+)/lines/(\d+)", path)
            if match:
                with self._write_connection() as conn:
                    project = update_project_line(conn, int(match.group(1)), int(match.group(2)), payload)
                    self._audit(conn, int(match.group(1)), 'Updated estimate item', 'Line ' + match.group(2) + ': ' + json.dumps({k: payload[k] for k in ('quantity', 'category_snapshot', 'notes', 'name_snapshot', 'reference_name', 'size_snapshot', 'supply_quantity_override', 'supply_unit_cost_override') if k in payload}, ensure_ascii=False))
                    project = self._estimate_delta(self._project_payload(conn, project),payload)
                    conn.commit()
                self._send_json({"success": True, **project})
                return
            if path == "/api/settings":
                allowed = {
                    "default_material_markup", "default_labor_rate", "default_overhead_markup",
                    "default_labor_hours_markup", "default_save_mode",
                    "currency", "llm_model", "llm_enabled", "default_crew_size", "default_hours_per_day"
                }
                values = {key: value for key, value in payload.items() if key in allowed}
                if "default_save_mode" in values and values["default_save_mode"] not in ("estimate", "update", "new"):
                    raise ValueError("Choose a valid default save destination")
                from conest_app.projects import crew_plan
                if 'default_crew_size' in values or 'default_hours_per_day' in values:
                    crew,hours=crew_plan({'crew_size':values.get('default_crew_size',2),'hours_per_day':values.get('default_hours_per_day',8)})
                    if 'default_crew_size' in values:values['default_crew_size']=crew
                    if 'default_hours_per_day' in values:values['default_hours_per_day']=hours
                if "default_labor_hours_markup" in values:
                    from conest_app.projects import labor_hours_markup
                    values["default_labor_hours_markup"]=labor_hours_markup(values["default_labor_hours_markup"])
                selected_model = clean_text(values.get("llm_model"))
                if selected_model and selected_model not in FREE_TIER_GEMINI_MODELS:
                    raise ValueError("Select a supported free-tier Gemini model")
                api_key = clean_text(payload.get("gemini_api_key"))
                if api_key:
                    values["gemini_api_key"] = api_key
                if payload.get("clear_gemini_api_key"):
                    values["gemini_api_key"] = ""
                values["llm_provider"] = "gemini"
                with self._write_connection() as conn:
                    update_settings(conn, values)
                    conn.commit()
                    settings = get_settings(conn)
                    configured = gemini_key_configured(conn)
                    stored = conn.execute("SELECT value FROM settings WHERE key='gemini_api_key'").fetchone()
                settings["llm_provider"] = "gemini"
                settings["llm_api_key_configured"] = configured
                settings["llm_api_key_source"] = (
                    "saved" if stored and stored[0].strip()
                    else "environment" if os.environ.get("GEMINI_API_KEY", "").strip()
                    else "none"
                )
                settings["llm_models"] = list(FREE_TIER_GEMINI_MODELS)
                settings["llm_free_tier_only"] = True
                self._send_json({"success": True, "settings": settings})
                return
            raise ApiError(404, "Route not found")
        except Exception as exc:
            self._handle_error(exc)

    def do_PUT(self) -> None:  # noqa: N802
        try:
            path, _ = self._route()
            if self._tender_route(path):return
            if self._productivity_route(path) or self._workspace_route(path):
                return
            self._guard(path)
            match = re.fullmatch(r"/api/catalog/(\d+)", path)
            if not match:
                raise ApiError(404, "Route not found")
            payload = self._json_body()
            with self._write_connection() as conn:
                capture_price(conn,int(match.group(1)),self.user['id'],{'source':'Before catalog edit'})
                item = update_manual_catalog_item(conn, int(match.group(1)), payload)
                capture_price(conn,item['id'],self.user['id'],payload)
                conn.commit()
            self._send_json({"success": True, "item": item})
        except Exception as exc:
            self._handle_error(exc)

    def do_DELETE(self) -> None:  # noqa: N802
        try:
            path, _ = self._route()
            if self._tender_route(path):return
            if self._productivity_route(path) or self._workspace_route(path):
                return
            self._guard(path)
            preview_match = re.fullmatch(r'/api/light-prices/previews/([a-f0-9]{32})', path)
            if preview_match:
                from conest_app import lighting_imports
                with self._read_connection() as conn:
                    lighting_imports.cancel_preview(preview_match[1], self.user)
                self._send_json({'success': True})
                return

            payload = self._json_body()
            catalog_match = re.fullmatch(r"/api/catalog/(\d+)", path)
            if catalog_match:
                from conest_app.catalog import delete_catalog_item
                with self._write_connection() as conn:
                    result=delete_catalog_item(conn,int(catalog_match[1]))
                    conn.commit()
                self._send_json({'success':True,**result})
                return
            project_match = re.fullmatch(r"/api/projects/(\d+)", path)
            if project_match:
                with self._write_connection() as conn:
                    check_revision(get_project(conn, int(project_match.group(1))), payload)
                    self._audit(conn, int(project_match.group(1)), 'Deleted project')
                    result = self._project_payload(conn, delete_project(conn, int(project_match.group(1))))
                    conn.commit()
                self._send_json({"success": True, **result})
                return
            match = re.fullmatch(r"/api/projects/(\d+)/lines/(\d+)", path)
            if match:
                with self._write_connection() as conn:
                    line = conn.execute("SELECT * FROM project_lines WHERE project_id=? AND id=?", (int(match[1]),int(match[2]))).fetchone()
                    if not line: raise LookupError("Estimate line not found")
                    check_revision(line, payload)
                    project = delete_project_line(conn, int(match.group(1)), int(match.group(2)))
                    self._audit(conn, int(match.group(1)), 'Removed estimate item', 'Line ' + match.group(2))
                    project = self._estimate_delta(self._project_payload(conn, project),payload)
                    conn.commit()
                self._send_json({"success": True, **project})
                return
            raise ApiError(404, "Route not found")
        except Exception as exc:
            self._handle_error(exc)


class ConEstServer(ThreadingHTTPServer):
    request_queue_size = 64
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        self._database_keeper = None
        self._backup_thread = None
        self._next_backup_check = 0
        super().__init__(*args, **kwargs)
        try:
            # Keep the WAL open throughout service. Request connections never
            # become the last connection and run an uncoordinated close checkpoint.
            self._database_keeper = connect()
            self._database_keeper.execute('SELECT version FROM schema_version').fetchone()
        except Exception:
            self.server_close()
            raise

    def service_actions(self):
        import time
        if time.monotonic()>=self._next_backup_check and not (self._backup_thread and self._backup_thread.is_alive()):
            self._next_backup_check=time.monotonic()+60
            def run_backup():
                try:backups.daily_backup()
                except Exception as exc:print('Daily database backup failed:',exc)
            self._backup_thread=threading.Thread(target=run_backup,daemon=True)
            self._backup_thread.start()

    def server_close(self):
        super().server_close()
        if self._backup_thread:self._backup_thread.join(timeout=30)
        if self._database_keeper is not None:
            self._database_keeper.close()
            self._database_keeper = None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TEC ConEst web application.")
    parser.add_argument("--host", default=os.environ.get("CONEST_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CONEST_PORT", "8080")))
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    initialize()
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    server = ConEstServer((args.host, args.port), ConEstHandler)
    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{display_host}:{args.port}"
    print("\nTEC ConEst is ready")
    print(f"  Open:     {url}")
    if args.host == "0.0.0.0":
        try:
            addresses = sorted({r[4][0] for r in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
                                if not r[4][0].startswith("127.")})
            for address in addresses:
                print(f"  Team URL: http://{address}:{args.port}")
        except OSError:
            pass
    print(f"  Database: {database_path()}")
    print("  Press Ctrl+C to stop.\n")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TEC ConEst...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
