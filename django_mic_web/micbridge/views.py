import json
import re
import uuid
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST


SESSION_ID_RE = re.compile(r"^[a-f0-9]{32}$")
MAX_SDP_LENGTH = 300_000
MAX_CANDIDATE_LENGTH = 8_000


class SignalingError(Exception):
    pass


def _documents_url(path=""):
    if not settings.FIREBASE_API_KEY:
        raise SignalingError("FIREBASE_API_KEY is missing. Copy it from the AirGuard google-services.json file into .env.")
    base = f"https://firestore.googleapis.com/v1/projects/{settings.FIREBASE_PROJECT_ID}/databases/(default)/documents"
    return f"{base}/{path}" if path else base


def _firestore(method, path, *, params=None, body=None, allow_404=False):
    query = {"key": settings.FIREBASE_API_KEY}
    query.update(params or {})
    try:
        response = requests.request(method, _documents_url(path), params=query, json=body, timeout=12)
    except requests.RequestException as exc:
        raise SignalingError("Could not reach the AirGuard Firestore backend.") from exc
    if allow_404 and response.status_code == 404:
        return None
    if not response.ok:
        raise SignalingError(f"Firestore returned HTTP {response.status_code}.")
    return response.json() if response.content else {}


def _decode_fields(document):
    decoded = {}
    for key, value in document.get("fields", {}).items():
        if "stringValue" in value:
            decoded[key] = value["stringValue"]
        elif "booleanValue" in value:
            decoded[key] = value["booleanValue"]
        elif "integerValue" in value:
            decoded[key] = int(value["integerValue"])
        elif "timestampValue" in value:
            decoded[key] = value["timestampValue"]
    return decoded


def _field(value):
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    return {"stringValue": str(value)}


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _valid_id(session_id):
    return bool(SESSION_ID_RE.fullmatch(session_id))


def _api_error(exc, status=502):
    return JsonResponse({"error": str(exc)}, status=status)


@ensure_csrf_cookie
def home(request):
    return render(request, "micbridge/home.html", {"ice_servers": settings.WEBRTC_ICE_SERVERS})


@require_POST
def create_session(request):
    session_id = uuid.uuid4().hex
    payload = {
        "fields": {
            "status": _field("waiting"),
            "offer": _field(""),
            "answer": _field(""),
            "createdAt": {"timestampValue": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")},
        }
    }
    try:
        _firestore("POST", "web_audio_sessions", params={"documentId": session_id}, body=payload)
    except SignalingError as exc:
        return _api_error(exc)
    return JsonResponse({"sessionId": session_id, "listenUrl": request.build_absolute_uri(f"/listen/?room={session_id}")})


@require_http_methods(["GET", "PATCH"])
def session_detail(request, session_id):
    if not _valid_id(session_id):
        return JsonResponse({"error": "Invalid session code."}, status=400)
    document_path = f"web_audio_sessions/{session_id}"
    try:
        if request.method == "GET":
            document = _firestore("GET", document_path, allow_404=True)
            if document is None:
                return JsonResponse({"error": "Session not found."}, status=404)
            return JsonResponse(_decode_fields(document))

        body = _json_body(request)
        if not isinstance(body, dict):
            return JsonResponse({"error": "Send valid JSON."}, status=400)
        allowed = {"offer", "answer", "status"}
        fields = {key: value for key, value in body.items() if key in allowed and isinstance(value, str)}
        if not fields or any(len(value) > MAX_SDP_LENGTH for value in fields.values()):
            return JsonResponse({"error": "No valid session fields were supplied."}, status=400)
        params = [("updateMask.fieldPaths", key) for key in fields]
        patch_body = {"fields": {key: _field(value) for key, value in fields.items()}}
        _firestore("PATCH", document_path, params=params, body=patch_body)
        return JsonResponse({"ok": True})
    except SignalingError as exc:
        return _api_error(exc)


@require_http_methods(["GET", "POST"])
def candidates(request, session_id, side):
    if not _valid_id(session_id) or side not in {"sender", "receiver"}:
        return JsonResponse({"error": "Invalid session or candidate type."}, status=400)
    collection = f"web_audio_sessions/{session_id}/{side}_candidates"
    try:
        if request.method == "POST":
            body = _json_body(request)
            candidate = body.get("candidate") if isinstance(body, dict) else None
            if not isinstance(candidate, str) or not candidate or len(candidate) > MAX_CANDIDATE_LENGTH:
                return JsonResponse({"error": "Invalid ICE candidate."}, status=400)
            candidate_id = uuid.uuid4().hex
            _firestore("POST", collection, params={"documentId": candidate_id}, body={"fields": {"candidate": _field(candidate)}})
            return JsonResponse({"ok": True, "id": candidate_id})

        result = _firestore("GET", collection, params={"pageSize": "100"})
        entries = []
        for document in result.get("documents", []):
            fields = _decode_fields(document)
            candidate_id = document.get("name", "").rsplit("/", 1)[-1]
            if candidate_id and fields.get("candidate"):
                entries.append({"id": candidate_id, "candidate": fields["candidate"]})
        return JsonResponse({"candidates": entries})
    except SignalingError as exc:
        return _api_error(exc)
