"""share.py — Draft storage payloads and self-contained share links.

Contracts: specs/001-editor-experience-upgrades/contracts/share-payload-contract.md
and data-model.md sections 7-8. Standard library only; import-free of Streamlit
so ``pytest`` runs it with no browser.

Numbers asserted by tests/test_share_codec.py and tests/test_document_migration.py:
  * share URL ceiling: 13 000 bytes (``tooLarge``, never a broken link)
  * payload schema version: 1 (``v`` in the link, ``version`` in the Draft)
  * draft write debounce/coalescing: >= 1000 ms after the last change
  * decode reasons: malformed | unsupportedVersion | truncated | emptyPayload
  * decode never raises and leaves the caller's live document untouched
"""

import base64
import json
import zlib

import appearance

# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

PAYLOAD_VERSION = 1               # SharePayload.v — mandatory, never guessed
DRAFT_VERSION = 1                 # Draft.version
LEGACY_DRAFT_VERSION = 0          # pre-schema draft shape, migrated (T033)
SHARE_URL_MAX_BYTES = 13000       # ceiling on the whole URL (FR-025)
DRAFT_MIN_INTERVAL_MS = 1000      # writes debounced/coalesced, SC-009
URL_PREFIX = "#p="
STORAGE_KEY_DRAFT = "mermaidGui.draft"
STORAGE_KEY_APPEARANCE = "mermaidGui.appearance"

DECODE_REASONS = ("malformed", "unsupportedVersion", "truncated", "emptyPayload")

# Plain-language messages the UI shows per reason (contract: fixed wording,
# one obvious dismissal path — "start a new diagram").
DECODE_MESSAGES = {
    "malformed": "This link is not a valid diagram link. "
                 "Start a new diagram to keep going.",
    "unsupportedVersion": "This link was made by a different version of the "
                          "editor. Start a new diagram to keep going.",
    "truncated": "This link is incomplete, probably cut short when it was "
                 "copied. Start a new diagram, or share a shorter diagram.",
    "emptyPayload": "This link carries no diagram. "
                    "Start a new diagram to keep going.",
}

_BASE64URL_ALPHABET = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=")


# ---------------------------------------------------------------------------
# Whole working state = source + name + knobs (the one shared content unit)
# ---------------------------------------------------------------------------

def make_knobs(scheme_name=None, base_colors=None, text_scale=None,
               font_family=None, density=None, path_emphasis=None,
               export_scale=None, export_background=None):
    """AppearanceKnobs built only from what the caller actually chose.

    Omitted knobs stay absent (rather than being pinned to defaults) so
    ``sourceOf`` keeps reporting layer 2 vs layer 3 honestly (contract 7).
    """
    knobs = {}
    for name, value in (("schemeName", scheme_name), ("baseColors", base_colors),
                        ("textScale", text_scale), ("fontFamily", font_family),
                        ("density", density), ("pathEmphasis", path_emphasis),
                        ("exportScale", export_scale),
                        ("exportBackground", export_background)):
        if value is not None:
            knobs[name] = value
    return knobs


def make_draft(source, name="", knobs=None, saved_at="",
               version=DRAFT_VERSION):
    """Draft dict (data-model section 7): the whole working state.

    ``savedAt`` is the ISO-8601 stamp the restore notice is labelled with
    (contract section 2 rule 6); callers in the browser pass ``new Date().toISOString()``.
    """
    return {
        "version": version,
        "savedAt": saved_at if isinstance(saved_at, str) else "",
        "source": source,
        "name": name,
        "knobs": dict(knobs) if isinstance(knobs, dict)
        else appearance.valid_knobs(knobs or {}),
    }


def validate_draft(draft):
    """True when ``draft`` has the shape the app may restore (never raises)."""
    if not isinstance(draft, dict):
        return False
    for key in ("version", "savedAt", "source", "name", "knobs"):
        if key not in draft:
            return False
    return (isinstance(draft["version"], int)
            and isinstance(draft["source"], str)
            and isinstance(draft["name"], str)
            and isinstance(draft["savedAt"], str)
            and isinstance(draft["knobs"], dict))


# ---------------------------------------------------------------------------
# Share link: fragment payload, compressed, URL-safe, size-ceiled
# ---------------------------------------------------------------------------

# URL-safe alphabet after compression. The leading token records the scheme so
# a future format change is a version decision, not a guess.
_COMPRESSION_TOKEN = "d1:"


def _compress(text):
    """deflate + URL-safe base64, padding stripped (research R-5).

    No ``+``, ``/`` or ``=`` survives into the fragment, so nothing else needs
    escaping, and zlib's checksum makes truncation detectable on decode.
    """
    compressor = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS)
    blob = compressor.compress(text.encode("utf-8")) + compressor.flush()
    raw = base64.urlsafe_b64encode(blob).decode("ascii").rstrip("=")
    return _COMPRESSION_TOKEN + raw


def _decompress(token):
    """Inverse of ``_compress``; raises with a reason tag the decoder classifies."""
    if not token.startswith(_COMPRESSION_TOKEN):
        if token and not set(token) <= _BASE64URL_ALPHABET:
            raise _DecodeFailure("malformed")
        raise _DecodeFailure("malformed")
    body = token[len(_COMPRESSION_TOKEN):]
    if not body:
        raise _DecodeFailure("emptyPayload")
    if not set(body) <= _BASE64URL_ALPHABET:
        raise _DecodeFailure("malformed")
    padded = body + "=" * (-len(body) % 4)
    try:
        blob = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception:
        raise _DecodeFailure("malformed")
    try:
        return zlib.decompress(blob).decode("utf-8")
    except zlib.error:
        raise _DecodeFailure("truncated")
    except UnicodeDecodeError:
        raise _DecodeFailure("truncated")


class _DecodeFailure(Exception):
    """Internal signal carrying the contract reason; never escapes decode()."""

    def __init__(self, reason):
        Exception.__init__(self, reason)
        self.reason = reason


def payload_from_document(source, knobs=None, name=None):
    """SharePayload (contract section 1): ``v``/``s``/``k`` (+ optional ``n``).

    Carries Knobs, never ResolvedAppearance (data-model section 4 invariant).
    """
    payload = {
        "v": PAYLOAD_VERSION,
        "s": source,
        "k": appearance.valid_knobs(knobs) if knobs else {},
    }
    if name:
        payload["n"] = name
    return payload


def encode_document(source, knobs=None, name=None, url_base=""):
    """Draft -> ShareLink dict (data-model section 8).

    ``tooLarge`` is decided on the byte length of the whole URL against the
    13 000-byte ceiling; a link known to be unreliable is never emitted.
    """
    payload = payload_from_document(source, knobs, name)
    body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"),
                      sort_keys=True)
    token = _compress(body)
    url = "%s%s%s" % (url_base, URL_PREFIX, token)
    size_bytes = len(url.encode("utf-8"))
    too_large = size_bytes > SHARE_URL_MAX_BYTES
    return {
        "payload": payload,
        # only URL-safe characters: no +, /, = needing further escaping
        "encoding": "deflate-base64url",
        "url": "" if too_large else url,
        "tooLarge": too_large,
        "sizeBytes": size_bytes,
    }


def encode_document_too_large(source, knobs=None, name=None, url_base=""):
    """True when this document must take the .mmd download path instead (FR-025)."""
    return bool(encode_document(source, knobs, name, url_base)["tooLarge"])


def fragment_of(url):
    """The encoded payload inside a share URL (or a bare fragment)."""
    if not isinstance(url, str):
        return ""
    marker = URL_PREFIX
    if marker in url:
        return url.split(marker, 1)[1]
    if url.startswith("#"):
        return url[1:]
    return url


def decode_document(raw):
    """Any string -> decoded SharePayload, or a typed decode error.

    Pure and total: never raises, for the empty string, truncated links,
    random text or a valid prefix plus garbage (FR-026). Out-of-range knob
    values are clamped to the nearest valid domain value, never rejected.
    """
    result = decode_fragment(raw if isinstance(raw, str) else "")
    if "knobs" in result:
        result["knobs"] = clamp_knobs(result.get("knobs"))
    return result


def decode_fragment(token):
    """Decode the ``#p=`` token itself (``decode_document`` accepts a whole URL)."""
    if not isinstance(token, str) or not token.strip():
        return decode_error("emptyPayload")
    fragment = fragment_of(token)
    if not fragment.strip():
        return decode_error("emptyPayload")
    try:
        body = _decompress(fragment.strip())
    except _DecodeFailure as failure:
        return decode_error(failure.reason)
    except Exception:
        return decode_error("malformed")
    try:
        payload = json.loads(body)
    except ValueError:
        return decode_error("malformed")
    if not isinstance(payload, dict):
        return decode_error("malformed")
    version = payload.get("v")
    if "v" not in payload:
        return decode_error("malformed")
    if not isinstance(version, int) or isinstance(version, bool):
        return decode_error("unsupportedVersion")
    if version != PAYLOAD_VERSION:
        return decode_error("unsupportedVersion")
    source = payload.get("s")
    if not isinstance(source, str):
        return decode_error("malformed")
    knobs = payload.get("k")
    if knobs is not None and not isinstance(knobs, dict):
        return decode_error("malformed")
    name = payload.get("n")
    if name is not None and not isinstance(name, str):
        return decode_error("malformed")
    defaulted = not isinstance(knobs, dict) or not knobs
    # contract section 3: an out-of-range value is clamped to the nearest valid
    # enum member, never rejected, so a hand-edited link cannot render at all.
    clean = clamp_knobs(knobs or {})
    result = {
        # the SharePayload field spellings of contract section 1, verbatim, so a
        # decoded link can be diffed against an encoded payload...
        "v": version,
        "s": source,
        "k": clean,
        # ...plus the Draft-shaped spellings app.py consumes (section 2), and the
        # explicit "defaulted" mark contract section 3 requires for a missing k.
        "source": source,
        "knobs": clean,
        "name": name or "",
        "knobsDefaulted": defaulted,
    }
    if name is not None:
        result["n"] = name
    return result


def decode_error(reason):
    """ShareLinkDecodeError as a value (contract: decode never throws)."""
    if reason not in DECODE_REASONS:
        reason = "malformed"
    return {
        "error": True,
        "reason": reason,
        "message": DECODE_MESSAGES[reason],
        "action": "start-new-diagram",
    }


def is_decode_error(result):
    return isinstance(result, dict) and result.get("error") is True


# ---------------------------------------------------------------------------
# Knob domain clamping (contract: out-of-range hand-edited values must not
# produce a false error state — SC-003)
# ---------------------------------------------------------------------------

def nearest_enum_value(value, domain):
    """Nearest valid member of ``domain`` for an out-of-range ``value``.

    Numeric values index the domain (``density: 99`` -> last value); strings
    fall back by prefix/suffix match, otherwise the catalog default (position
    of DEFAULT_KNOBS) is used. Never raises.
    """
    if value in domain:
        return value
    if isinstance(value, bool):
        return _domain_default(domain)
    if isinstance(value, (int, float)):
        index = int(value)
        if index < 0:
            index = 0
        if index >= len(domain):
            index = len(domain) - 1
        return domain[index]
    if isinstance(value, str):
        target = value.strip().lower()
        for member in domain:
            if member.lower() == target:
                return member
        for member in domain:
            if member.lower().startswith(target) or target.startswith(member.lower()):
                return member
        for member in domain:
            if target in member.lower() or member.lower() in target:
                return member
    return _domain_default(domain)


def _domain_default(domain):
    """The catalog default inside a domain, else the first member."""
    for name, default in appearance.DEFAULT_KNOBS.items():
        if name in appearance.KNOB_DOMAINS and default in domain:
            return default
    return domain[0]


def clamp_knobs(knobs):
    """Every knob forced into its domain via nearest_enum_value."""
    if not isinstance(knobs, dict):
        return {}
    clean = {}
    for name, domain in appearance.KNOB_DOMAINS.items():
        if name in knobs:
            clean[name] = nearest_enum_value(knobs[name], domain)
    base = knobs.get("baseColors")
    if base is None:
        if "baseColors" in knobs:
            clean["baseColors"] = None
    elif isinstance(base, dict) and appearance.is_hex_color(base.get("background")) \
            and appearance.is_hex_color(base.get("foreground")):
        clean["baseColors"] = {"background": base["background"].lower(),
                               "foreground": base["foreground"].lower()}
    else:
        clean["baseColors"] = None
    for name in ("exportScale",):
        if name in knobs:
            clean[name] = nearest_enum_value(knobs[name], appearance.EXPORT_SCALES)
    if "exportBackground" in knobs:
        background = knobs["exportBackground"]
        if background in appearance.EXPORT_BACKGROUND_WORDS:
            clean["exportBackground"] = background
        elif appearance.is_hex_color(background):
            clean["exportBackground"] = background.lower()
        else:
            clean["exportBackground"] = appearance.DEFAULT_KNOBS["exportBackground"]
    unknown = set(knobs) - set(clean) - {"baseColors", "exportScale",
                                         "exportBackground"}
    for name in sorted(unknown):
        clean[name] = knobs[name]
    return clean


# ---------------------------------------------------------------------------
# Draft version migration (data-model section 7: migrate or ignore, never crash)
# ---------------------------------------------------------------------------

def migrate_document(draft):
    """Any stored draft -> current-version Draft, or ``None`` to discard.

    Unknown/undated versions have no migration entry, so they are discarded
    silently; nothing ever raises and no stack trace can surface (spec edge
    case 'drafts from an older version').
    """
    if not isinstance(draft, dict):
        return None
    version = draft.get("version")
    if version is None:
        # the true pre-schema shape carries no version field at all: it is v0
        if not any(key in draft for key in ("text", "appearance", "updatedAt",
                                            "source")):
            return None
        version = LEGACY_DRAFT_VERSION
    if isinstance(version, bool) or not isinstance(version, int):
        return None
    if version == DRAFT_VERSION:
        return draft if validate_draft(draft) else None
    migration = _MIGRATIONS.get(version)
    if migration is None:
        return None
    try:
        migrated = migration(draft)
    except Exception:
        return None
    if not validate_draft(migrated):
        return None
    return migrated


def _migrate_v0_to_v1(draft):
    """Pre-schema draft: ``{updatedAt, appearance, type, text}`` -> Draft v1.

    Field renames per research R-5's original draft shape; the diagram text
    moves to ``source``, the look to ``knobs`` (source/name/knobs is the one
    content unit both formats share).
    """
    source = draft.get("source")
    if not isinstance(source, str):
        source = draft.get("text")
    if not isinstance(source, str):
        source = draft.get("code")
    if not isinstance(source, str):
        return None
    saved_at = draft.get("savedAt")
    if not isinstance(saved_at, str):
        saved_at = draft.get("updatedAt")
    if not isinstance(saved_at, str):
        saved_at = ""
    name = draft.get("name")
    if not isinstance(name, str):
        name = ""
    knobs = draft.get("knobs")
    if not isinstance(knobs, dict):
        knobs = draft.get("appearance") if isinstance(draft.get("appearance"), dict) \
            else {}
    return {
        "version": DRAFT_VERSION,
        "savedAt": saved_at,
        "source": source,
        "name": name,
        "knobs": appearance.valid_knobs(knobs),
    }


_MIGRATIONS = {
    LEGACY_DRAFT_VERSION: _migrate_v0_to_v1,
}


def parse_draft_json(raw_json):
    """localStorage string -> restore candidate (migrated) or ``None``.

    Invalid JSON, unknown shapes and un-migratable versions all discard
    silently; the caller keeps the user's live document untouched (FR-026).
    """
    try:
        loaded = json.loads(raw_json)
    except (TypeError, ValueError):
        return None
    return migrate_document(loaded)


def draft_is_storable(draft):
    """True when this Draft may be written (current or migratable version)."""
    return isinstance(draft, dict) and draft.get("version") == DRAFT_VERSION


# ---------------------------------------------------------------------------
# Draft write scheduling (contract section 2 rule 1: >= 1000 ms, coalesced)
# ---------------------------------------------------------------------------

DRAFT_DEBOUNCE_MS = DRAFT_MIN_INTERVAL_MS


class DraftScheduler(object):
    """Debounced, coalescing gate for draft writes (contract section 2 rule 1).

    The wait is measured from the **last change**: a write may not happen until
    at least ``min_interval_ms`` after typing stopped, and every newer change
    replaces the pending draft, so a burst of keystrokes costs one write.
    """

    def __init__(self, min_interval_ms=DRAFT_MIN_INTERVAL_MS, clock_ms=None):
        if min_interval_ms < DRAFT_MIN_INTERVAL_MS:
            raise ValueError("draft writes must be debounced by at least %d ms"
                             % DRAFT_MIN_INTERVAL_MS)
        self.min_interval_ms = min_interval_ms
        self._clock_ms = clock_ms
        self._last_change_ms = None
        self._last_write_ms = None
        self._pending = None

    def _now_ms(self):
        if self._clock_ms is not None:
            return int(self._clock_ms())
        import time
        return int(time.monotonic() * 1000)

    def note_change(self, draft):
        """Record the newest draft; an earlier pending write is coalesced away."""
        self._pending = draft
        self._last_change_ms = self._now_ms()
        return self._pending

    def pending(self):
        return self._pending

    def write_count_hint(self):
        """Writes issued so far - tests assert a keystroke burst costs one."""
        return 0 if self._last_write_ms is None else 1

    def due_ms(self):
        """Milliseconds until the pending write may run (None when idle)."""
        if self._pending is None:
            return None
        elapsed = self._now_ms() - self._last_change_ms
        remaining = self.min_interval_ms - elapsed
        return remaining if remaining > 0 else 0

    def flush(self):
        """Return the pending draft when the debounce has fully elapsed, else None."""
        if self._pending is None:
            return None
        if self.due_ms():
            return None
        draft = self._pending
        self._pending = None
        self._last_write_ms = self._now_ms()
        return draft
