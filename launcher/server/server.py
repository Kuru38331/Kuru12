"""Explicit local-profile experiment, NOT a verified HSHO/Steam backend."""
import argparse
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import os
import secrets
import threading
import time
from character_selection import load_catalog, apply_selection
from character_state import CharacterState

ROOT = Path(__file__).parent
AUTH = '/live/player/authen'
PRODUCTS = '/live/productlisting/list'
ITEMS = '/live/item/listall'
SLOT_GET = '/live/player/characterslot/get'
SLOT_EDIT = '/live/player/characterslot/edit'
INVENTORY = '/live/player/inventory/getAll'
STORE = '/live/store/list'
CURSE_RELIC = '/live/player/curserelic/get'
IMPLEMENTED = (AUTH, PRODUCTS, ITEMS, SLOT_GET, SLOT_EDIT, INVENTORY, STORE, CURSE_RELIC)
FIELDS = {'authType': str, 'ticket': str, 'clientversion': str, 'macaddress': str}
LIMIT = 65536


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, port=18080, local_profile=False, observations=None,
                 visitor=None, warden=None, role=None, allow_special=False, state_path=None):
        self.local_profile = local_profile
        self.profile = json.loads((ROOT/'experimental-profile.json').read_text())['response']
        local_id=os.environ.get('HSHO_LOCAL_PLAYER_ID') or ('local-'+secrets.token_hex(12))
        if not local_id.startswith('local-') or len(local_id)!=30 or any(c not in '0123456789abcdef' for c in local_id[6:]):
            raise ValueError('Invalid local profile id')
        self.profile['data']['player']['_id']=local_id
        display_name=os.environ.get('HSHO_LOCAL_DISPLAY_NAME')
        if display_name is not None:
            if not display_name.strip() or len(display_name)>128 or any(ord(c)<32 or ord(c)==127 for c in display_name):
                raise ValueError('Invalid local display name')
            self.profile['data']['player']['profile']['displayName']=display_name
        if visitor is not None or warden is not None or role is not None:
            self.profile = apply_selection(self.profile, load_catalog(), visitor, warden,
                                           role, allow_special)
        self.observations = observations
        catalog_path = ROOT/'known-routes.json'
        catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else {}
        self.known_routes = set(IMPLEMENTED) | {'/health'} | {
            row['route'] for row in catalog.get('routes', [])}
        self.known_fields = set(FIELDS) | set(catalog.get('known_request_fields', []))
        self.lock = threading.Lock()
        # Only one local development identity; no Steam identity or ticket is stored.
        self.session = None
        self.session_expires = 0
        self.characters = CharacterState(self.profile, load_catalog(), state_path, allow_special)
        if visitor is not None or warden is not None or role is not None:
            choice = {'slots': {}}
            if visitor is not None:
                choice['slots']['characteritem'] = visitor
            if warden is not None:
                choice['slots']['characterhunteritem'] = warden
            if role is not None:
                choice['role'] = role
            self.characters.update(choice, persist=False)
        super().__init__(('127.0.0.1', port), Handler)

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(5)
        return sock, address


class Handler(BaseHTTPRequestHandler):
    server_version = 'HSHOLocalExperiment/0.1'
    def log_message(self, *args):
        pass  # Default access logs can expose query values.

    def reply(self, code, payload):
        route = '/'+'/'.join(p for p in self.path.split('?', 1)[0].split('/') if p)
        self.observe(route, getattr(self, 'observation_body', None), code)
        raw = json.dumps(payload, allow_nan=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def observe(self, route, body=None, response_status=None):
        # Record only a fixed route label and known field type names, never values,
        # arbitrary input keys, headers, query strings, tickets or tokens.
        record = {'schemaVersion': 2, 'time': int(time.time()), 'method': self.command,
                  'route': route if route in self.server.known_routes else 'unknown',
                  'response_status': response_status,
                  'known_field_types': {k: type(body[k]).__name__ for k in self.server.known_fields
                                        if isinstance(body, dict) and k in body}}
        if self.server.observations:
            with self.server.lock:
                with Path(self.server.observations).open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(record)+'\n')

    def do_GET(self):
        if self.path == '/health':
            return self.reply(200, {'mode': 'local-profile-experiment',
                'enabled': self.server.local_profile, 'steamIdentityVerified': False,
                'realClientMenuVerified': False})
        self.reply(405, {'status': 0, 'error': 'post_required'})

    def do_POST(self):
        # Routing override uses trailing slashes to preserve compiled bytecode size.
        # Normalize separators without treating a URL supplied by the caller as a host.
        path = '/'+'/'.join(p for p in self.path.split('?', 1)[0].split('/') if p)
        # Unknown paths are never printed. Recognized, unimplemented route labels
        # are useful evidence when trying character selection and training modes.
        if self.headers.get('Transfer-Encoding'):
            return self.reply(400, {'status': 0, 'error': 'transfer_encoding_unsupported'})
        lengths = self.headers.get_all('Content-Length', [])
        try:
            if len(lengths) != 1:
                raise ValueError()
            length = int(lengths[0])
        except ValueError:
            return self.reply(400, {'status': 0, 'error': 'invalid_content_length'})
        if not 0 <= length <= LIMIT:
            return self.reply(413, {'status': 0, 'error': 'body_too_large'})
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            return self.reply(415, {'status': 0, 'error': 'json_required'})
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError()
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError()
        except (ValueError, UnicodeError, OSError, RecursionError):
            return self.reply(400, {'status': 0, 'error': 'invalid_json_body'})
        self.observation_body = body
        if path not in IMPLEMENTED:
            return self.reply(501, {'status': 0, 'error': 'route_not_implemented'})
        if not self.server.local_profile:
            return self.reply(503, {'status': 0, 'error': 'local_profile_mode_disabled'})
        if path == AUTH:
            if any(type(body.get(k)) is not typ for k, typ in FIELDS.items()):
                return self.reply(400, {'status': 0, 'error': 'authentication_fields_missing_or_wrong_type'})
            if body['authType'] != 'steam' or not body['ticket']:
                return self.reply(400, {'status': 0, 'error': 'unsupported_authentication_input'})
            # Explicit development mode: input ticket is discarded, NOT validated.
            # This grants access only to this local test profile and no Steam account.
            response = self.server.characters.response()
            with self.server.lock:
                self.server.session = secrets.token_hex(32)
                self.server.session_expires = time.monotonic()+3600
                response['data']['player']['session_token'] = self.server.session
            response['localExperiment'] = {'steamIdentityVerified': False}
            return self.reply(200, response)
        if path in (SLOT_GET, SLOT_EDIT, INVENTORY, STORE, CURSE_RELIC):
            token = body.get('session_token')
            with self.server.lock:
                valid = (isinstance(token, str) and len(token) == 64 and token.isascii()
                         and self.server.session is not None
                         and time.monotonic() < self.server.session_expires
                         and secrets.compare_digest(token, self.server.session))
            if not valid:
                return self.reply(401, {'status': 0, 'error': 'invalid_local_session'})
            if path == CURSE_RELIC:
                return self.reply(200, {'status': 1, 'data': {'curseRelic': copy.deepcopy(self.server.characters.loadouts['curseRelic'])}})
            if path == STORE:
                # Source reader YGG GS Get Storelist accepts an empty data.store array.
                # Owned skins are supplied separately through inventory/getAll.
                return self.reply(200, {'status': 1, 'data': {'store': []}})
            if path == INVENTORY:
                return self.reply(200, self.server.characters.inventory())
            try:
                if path == SLOT_EDIT:
                    edit = {k: v for k, v in body.items() if k != 'session_token'}
                    result = self.server.characters.update(edit)
                else:
                    result = self.server.characters.response()
            except ValueError:
                return self.reply(400, {'status': 0, 'error': 'invalid_character_selection'})
            except OSError:
                return self.reply(507, {'status': 0, 'error': 'local_character_save_failed'})
            result['data']['player']['session_token'] = self.server.session
            return self.reply(200, result)
        # Both observed catalog calls pass Authorize=false in the supplied asset.
        # Empty arrays follow a branch in the regular cache; optimized path unverified.
        key = 'productListing' if path == PRODUCTS else 'items'
        self.reply(200, {'status': 1, 'data': {key: []}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-profile-experiment', action='store_true',
                        help='Explicitly enable speculative local test responses; no Steam verification')
    parser.add_argument('--visitor', help='Exact visitor Character item name from exported asset catalog')
    parser.add_argument('--warden', help='Exact warden Character item name from exported asset catalog')
    parser.add_argument('--role', choices=('survivor', 'hunter'))
    parser.add_argument('--allow-special-character-assets', action='store_true')
    parser.add_argument('--list-character-assets', action='store_true')
    parser.add_argument('--character-state-file', type=Path, default=ROOT/'local-character-state.json')
    args = parser.parse_args()
    if args.list_character_assets:
        for name, row in sorted(load_catalog().items()):
            print(name, row['faction'], 'resolved' if row['selection_metadata_complete'] else 'UNRESOLVED',
                  'special' if row['special_asset'] else 'regular')
        raise SystemExit(0)
    server = Server(local_profile=args.local_profile_experiment,
                    observations=ROOT/'observations.jsonl', visitor=args.visitor, warden=args.warden,
                    role=args.role, allow_special=args.allow_special_character_assets,
                    state_path=args.character_state_file)
    print('http://127.0.0.1:18080 — LOCAL EXPERIMENT ONLY; menu access unverified.', flush=True)
    print('No Steam identity validation; no public service. Ctrl+C to stop.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
