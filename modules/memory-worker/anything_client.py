import os
import requests
import json
import tempfile
import hashlib
import logging
from typing import Tuple, Dict, Any, Optional
import config as worker_config

logger = logging.getLogger("anything_client")
logger.setLevel(logging.INFO)

BASE_URL = (os.getenv("ANYTHING_LLM_HOST") or "http://ia-anythingllm:3001").strip().rstrip('/')
API_KEY = os.getenv("ANYTHING_LLM_API_KEY")
ARCHIVE_DIR = worker_config.ARCHIVE_DEFAULT_PATH
MD_DIR = worker_config.MD_DEFAULT_PATH


def _headers():
    h = {}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h


def upload_document(content, filename, workspace_slug, timeout=60):
    """Upload a markdown/string as a document to AnythingLLM.
    Returns (doc_id, full_response_dict) on success, (None, resp) on failure.
    """
    upload_url = f"{BASE_URL}/api/v1/document/upload"
    files = {'file': (filename, content, 'text/markdown')}
    try:
        r = requests.post(upload_url, headers=_headers(), files=files, timeout=timeout)
    except Exception as e:
        logger.warning(f"[upload] connection error: {e}")
        return None, None

    try:
        resp = r.json()
        logger.debug(f"[upload] response keys: {list(resp.keys())}")
    except Exception:
        resp = {'status_code': r.status_code, 'text': r.text}
        logger.debug(f"[upload] non-json response, status: {r.status_code}")

    # Consider success if server returned success flag, regardless of exact status
    if isinstance(resp, dict) and resp.get('success'):
        # Try to discover document id in common places
        # 1) top-level keys
        for k in ('id', 'document_id', 'doc_id', 'file_id'):
            if resp.get(k):
                return resp.get(k), resp
        # 2) documents list (anythingllm often returns {'documents':[{'id':...}]})
        try:
            docs = resp.get('documents')
            logger.debug(f"[upload] documents present: {isinstance(docs, list)}")
            if isinstance(docs, list) and len(docs) > 0:
                first = docs[0]
                if isinstance(first, dict) and first.get('id'):
                    logger.debug(f"[upload] found id in documents[0]: {first.get('id')}")
                    return first.get('id'), resp
        except Exception:
            pass
        # 3) nested data
        data = resp.get('data')
        if isinstance(data, dict):
            for k in ('id', 'document_id', 'doc_id', 'file_id'):
                if data.get(k):
                    return data.get(k), resp
        # 4) try scanning for id-like strings anywhere in the payload (best-effort)
        try:
            # scan documents entries for any id-like field
            if isinstance(resp, dict):
                for v in resp.values():
                    if isinstance(v, list):
                        for it in v:
                            if isinstance(it, dict) and it.get('id'):
                                return it.get('id'), resp
        except Exception:
            pass

        # If we reach here we got success but couldn't find an id; return whole resp
        logger.warning(f"[upload] success but no id found in response: keys={list(resp.keys())}")
        return None, resp
    else:
        logger.warning(f"[upload] server rejected upload: {r.status_code} {r.text}")
        return None, resp


def delete_document(doc_id, workspace_slug=None, timeout=30):
    """Try several deletion endpoints. Return True if any deletion reports success."""
    if not doc_id:
        return False

    logger.debug(f"[delete] Attempting to delete document {doc_id}, workspace: {workspace_slug}")

    # 1) Try DELETE /api/v1/document/{id}
    try:
        url = f"{BASE_URL}/api/v1/document/{doc_id}"
        r = requests.delete(url, headers=_headers(), timeout=timeout)
        logger.debug(f"[delete] DELETE endpoint response: {r.status_code} {r.text}")
        if r.status_code in (200, 204):
            logger.info(f"[delete] Deleted document {doc_id} via DELETE endpoint")
            return True
    except Exception as e:
        logger.debug(f"[delete] DELETE attempt failed: {e}")

    # 2) Try POST /api/v1/document/delete {ids: [...]} (some servers use this)
    try:
        url = f"{BASE_URL}/api/v1/document/delete"
        r = requests.post(url, headers={**_headers(), 'Content-Type': 'application/json'}, json={'ids': [doc_id]}, timeout=timeout)
        logger.debug(f"[delete] Bulk delete response: {r.status_code} {r.text}")
        if r.status_code == 200 and (r.json().get('success') or r.json().get('deleted')):
            logger.info(f"[delete] Deleted document {doc_id} via bulk delete")
            return True
    except Exception as e:
        logger.debug(f"[delete] bulk delete attempt failed: {e}")

    # 3) Workspace-scoped delete: POST /api/v1/workspace/{ws}/document/{id}/delete
    if workspace_slug:
        try:
            url = f"{BASE_URL}/api/v1/workspace/{workspace_slug}/document/{doc_id}/delete"
            r = requests.post(url, headers=_headers(), timeout=timeout)
            logger.debug(f"[delete] Workspace delete response: {r.status_code} {r.text}")
            if r.status_code == 200 and r.json().get('success'):
                logger.info(f"[delete] Deleted document {doc_id} via workspace-scoped endpoint")
                return True
        except Exception as e:
            logger.debug(f"[delete] workspace delete attempt failed: {e}")

    logger.warning(f"[delete] Unable to delete document {doc_id} - tried multiple endpoints")
    return False


def trigger_embeddings(workspace_slug, timeout=30):
    try:
        url = f"{BASE_URL}/api/v1/workspace/{workspace_slug}/update-embeddings"
        r = requests.post(url, headers=_headers(), timeout=timeout)
        if r.status_code == 200:
            logger.info(f"[embeddings] Triggered embeddings for workspace {workspace_slug}")
            return True
        logger.warning(f"[embeddings] Non-200 response: {r.status_code} {r.text}")
    except Exception as e:
        logger.warning(f"[embeddings] Error triggering embeddings: {e}")
    return False


def _read_manifest():
    path = os.path.join(ARCHIVE_DIR, 'manifest.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _write_manifest(manifest):
    path = os.path.join(ARCHIVE_DIR, 'manifest.json')
    try:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        with tempfile.NamedTemporaryFile('w', delete=False, dir=ARCHIVE_DIR, encoding='utf-8') as tf:
            json.dump(manifest, tf, ensure_ascii=False, indent=2)
            tmp = tf.name
        os.replace(tmp, path)
        return True
    except Exception:
        logger.exception(f"[manifest] Failed to write manifest to {path}.")
        return False


def find_entry_by_filename(filename):
    manifest = _read_manifest()
    for k, v in manifest.items():
        if v.get('filename') == filename or v.get('filepath', '').endswith(filename):
            return k, v
    return None, None


def update_entry_docid(filename, doc_id):
    manifest = _read_manifest()
    changed = False
    for k, v in manifest.items():
        if v.get('filename') == filename or v.get('filepath', '').endswith(filename):
            # Set previous to current before updating
            if 'any_document_id' in v:
                v['previous_any_document_id'] = v['any_document_id']
            v['any_document_id'] = doc_id
            manifest[k] = v
            changed = True
            break
    if not changed:
        # Add new entry if not found
        key = filename  # use filename as key
        manifest[key] = {
            'filename': filename,
            'any_document_id': doc_id
        }
        changed = True
    if changed:
        return _write_manifest(manifest)
    return False

def update_entry_timestamp(filename, timestamp):
    manifest = _read_manifest()
    changed = False
    for k, v in manifest.items():
        if v.get('filename') == filename or v.get('filepath', '').endswith(filename):
            v['last_message_timestamp'] = timestamp
            manifest[k] = v
            changed = True
            break
    if changed:
        return _write_manifest(manifest)
    return False
