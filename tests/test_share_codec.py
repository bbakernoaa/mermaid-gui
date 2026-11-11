"""Share-payload contract tests: round-trip, ceiling, decode totality, reasons."""

import json

import pytest

import share

CEILING = share.SHARE_URL_MAX_BYTES
SOURCE = "flowchart TD\n  A-->B\n  B-->C{decision}"
NAME = "Release flow"
URL_BASE = "https://mermaid-gui.example/mermaid-gui/"

UNICODE_SOURCE = (
    "classDiagram\n"
    "    class Café<<interface>> { «attr» }\n"
    "   class 数据处理 { +映射() }\n"
    "    class Кириллица\n"
    "    Cafe <|.. Кириллица : «наследует» {\"json\": ['braces']}\n"
    "    %% 🔎 emoji in a comment\n"
)


def _decode_url(result):
    return share.decode_document(result["url"])


def test_encode_produces_fragment_url_and_payload():
    result = share.encode_document(SOURCE, share.make_knobs(), NAME, URL_BASE)
    assert result["tooLarge"] is False
    assert result["url"].startswith(URL_BASE + share.URL_PREFIX)
    assert result["payload"] == {"v": share.PAYLOAD_VERSION, "s": SOURCE,
                                 "k": share.make_knobs(), "n": NAME}
    assert result["sizeBytes"] == len(result["url"].encode("utf-8"))
    assert CEILING == 13000


def test_name_is_omitted_when_the_user_never_named_the_diagram():
    payload = share.encode_document(SOURCE)["payload"]
    assert "n" not in payload
    assert sorted(payload) == ["k", "s", "v"]


def test_urlsafe_alphabet_needs_no_further_escaping():
    # a long, varied source maximises the chance of producing + / = in base64
    source = "\n".join("node%d[label %d] --> node%d" % (i, i, i + 1)
                       for i in range(60))
    url = share.encode_document(source, share.make_knobs(), "Alphabet check",
                                URL_BASE)["url"]
    token = share.fragment_of(url)
    for character in ("+", "/", "="):
        assert character not in token
    assert " " not in token and "%" not in token


def test_plain_round_trip_is_byte_identical():
    result = share.encode_document(SOURCE, share.make_knobs(), NAME, URL_BASE)
    decoded = _decode_url(result)
    assert decoded["s"] == SOURCE
    assert decoded["n"] == NAME
    assert decoded["v"] == share.PAYLOAD_VERSION
    assert decoded["knobs"] == share.make_knobs()
    assert share.is_decode_error(decoded) is False


@pytest.mark.parametrize("source", [
    UNICODE_SOURCE,
    "flowchart TD\n  A['quote'] --> B[\"double\"]",
    "journey\n  title Emoji 🎨 ✅\n  section S\n    A: 3: Me\n",
    "sequenceDiagram\n  participant A\n  A->>B: {\"json\": [1, 2]}\n",
    "erDiagram\n  DOC ||--o{ REV : has\n",
])
def test_round_trip_preserves_unicode_quotes_and_braces(source):
    for name in (None, "Named 😺"):
        result = share.encode_document(source, share.make_knobs(), name)
        decoded = _decode_url(result)
        assert decoded["tooLarge"] is False if "tooLarge" in decoded else True
        assert result["tooLarge"] is False
        assert decoded["s"] == source
        assert decoded.get("n") == name


def test_decode_accepts_a_whole_url_a_fragment_or_a_bare_token():
    url = share.encode_document(SOURCE, name=NAME)["url"]
    token = share.fragment_of(url)
    for candidate in (url, "#p=" + token, token):
        assert share.decode_document(candidate)["s"] == SOURCE


def test_unknown_type_in_payload_still_decodes():
    """Decode is not a validator: an unknown diagram type is the bridge's job."""
    source = "timeline\n    Title X\n    Section Y : Z\n"
    url = share.encode_document(source)["url"]
    assert share.decode_document(url)["s"] == source


def test_payload_without_knobs_decodes_with_explicit_defaults():
    body = json.dumps({"v": share.PAYLOAD_VERSION, "s": SOURCE})
    token = share._compress(body)
    decoded = share.decode_document("#p=" + token)
    assert decoded["s"] == SOURCE
    assert decoded["knobs"] == share.make_knobs()
    assert decoded["knobsDefaulted"] is True


def test_out_of_range_enum_knob_is_clamped_never_rejected():
    body = json.dumps({"v": share.PAYLOAD_VERSION, "s": SOURCE,
                       "k": {"density": 99, "schemeName": "bogus",
                             "textScale": "roomy"}})
    decoded = share.decode_document("#p=" + share._compress(body))
    assert share.is_decode_error(decoded) is False
    assert decoded["k"]["density"] in share.appearance.DENSITIES
    assert decoded["k"]["schemeName"] in share.appearance.SCHEME_NAMES
    assert decoded["k"]["textScale"] in share.appearance.TEXT_SCALES


def test_missing_knobs_key_decodes_with_explicit_defaults():
    body = json.dumps({"v": share.PAYLOAD_VERSION, "s": SOURCE})
    decoded = share.decode_document("#p=" + share._compress(body))
    assert decoded["knobs"] == share.make_knobs()
    assert decoded["s"] == SOURCE
    assert decoded["name"] == ""
    assert "n" not in decoded            # optional field omitted, per contract


def test_non_object_knobs_is_rejected_without_raising():
    body = json.dumps({"v": share.PAYLOAD_VERSION, "s": SOURCE, "k": "oops"})
    result = share.decode_document("#p=" + share._compress(body))
    assert result["error"] is True
    assert result["reason"] == "malformed"


# ---------------------------------------------------------------------------
# 13 000-byte ceiling (measured on the whole URL, in bytes)
# ---------------------------------------------------------------------------

def _padded_base(target_bytes, reference_bytes):
    """A URL base that makes the finished URL exactly ``target_bytes`` long."""
    pad = target_bytes - reference_bytes
    assert pad > 8, (target_bytes, reference_bytes)
    return "https://" + "p" * (pad - 9) + "/"


def test_at_exactly_13000_bytes_the_link_is_still_emitted():
    bare = share.encode_document(SOURCE, share.make_knobs(), NAME, "")
    assert bare["sizeBytes"] == len(bare["url"].encode("utf-8"))
    base = _padded_base(CEILING, bare["sizeBytes"])
    result = share.encode_document(SOURCE, share.make_knobs(), NAME, base)
    assert result["sizeBytes"] == CEILING
    assert result["tooLarge"] is False
    assert result["url"].startswith(base)
    assert share.encode_document_too_large(SOURCE, share.make_knobs(), NAME,
                                           base) is False
    assert share.decode_document(result["url"])["s"] == SOURCE


def test_one_byte_over_the_ceiling_is_refused_not_emitted():
    bare = share.encode_document(SOURCE, share.make_knobs(), NAME, "")
    base = _padded_base(CEILING + 1, bare["sizeBytes"])
    result = share.encode_document(SOURCE, share.make_knobs(), NAME, base)
    assert result["sizeBytes"] == CEILING + 1
    assert result["tooLarge"] is True
    assert result["url"] == ""            # never emit a link known to be unreliable
    assert result["payload"]["s"] == SOURCE  # payload still available for the UI copy
    assert share.encode_document_too_large(SOURCE, share.make_knobs(), NAME,
                                           base) is True


def test_incompressible_documents_cross_the_ceiling():
    """Random-looking labels cannot be deflated away, so a long document is
    reported as tooLarge and the UI takes the .mmd download path (FR-025)."""
    def doc(target_nodes):
        lines = ["flowchart TD"]
        value = 12345
        for i in range(target_nodes):
            value = (value * 1103515245 + 12345) % (2 ** 31)
            lines.append("  n%04x[label %08x] --> n%04x" % (value % 4096, value,
                                                            (value >> 7) % 4096))
        return "\n".join(lines) + "\n"

    small = share.encode_document(doc(30), url_base=URL_BASE)
    assert small["tooLarge"] is False and small["url"]
    big = share.encode_document(doc(3000), url_base=URL_BASE)
    assert big["tooLarge"] is True and big["url"] == ""
    assert big["sizeBytes"] > CEILING


def test_max_size_document_never_yields_a_link():
    """50 000 chars (data-model section 1 ceiling) must take the download path."""
    filler = []
    value = 7919
    for i in range(2600):
        value = (value * 1103515245 + 12345) % (2 ** 31)
        filler.append("  q%05d[node %08x] --> r%05d" % (i, value, i + 1))
    body = "\n".join(filler)
    source = "flowchart TD\n" + body
    while len(source) < 50000:
        value = (value * 1103515245 + 12345) % (2 ** 31)
        filler.append("  s%08x" % value)
        source = "flowchart TD\n" + "\n".join(filler)
    assert len(source) >= 50000
    assert share.encode_document_too_large(source, url_base=URL_BASE) is True
    assert share.encode_document(source, url_base=URL_BASE)["url"] == ""
    draft = share.make_draft(source)
    assert share.validate_draft(draft) is True
    assert draft["source"] == source


def test_ceiling_is_checked_on_bytes_not_characters():
    """The payload is serialised with ensure_ascii, so the token is pure ASCII:
    byte length equals character length and the ceiling never moves."""
    named = share.encode_document(SOURCE, share.make_knobs(), "é" * 40, "")
    assert named["payload"]["s"] == SOURCE
    token = share.fragment_of(named["url"])
    # ensure_ascii serialisation keeps the whole URL single-byte
    assert all(ord(char) < 128 for char in named["url"])
    assert named["sizeBytes"] == len(named["url"])
    assert "é" not in named["url"]
    assert share.decode_document(named["url"])["n"] == "é" * 40
    # the URL length in bytes is what the ceiling compares against
    long_base = _padded_base(CEILING + 1, named["sizeBytes"])
    assert share.encode_document(SOURCE, share.make_knobs(), "é" * 40,
                                 long_base)["tooLarge"] is True
    assert share.encode_document(SOURCE, share.make_knobs(), "é" * 40,
                                 _padded_base(CEILING, named["sizeBytes"])
                                 )["tooLarge"] is False


# ---------------------------------------------------------------------------
# Decoding is total: every input returns a value, never an exception
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    "", "   ", "not-a-link", "#", "#p=", "#p=%%%zzz", "#p=" + "A" * 5000,
    "https://x.example/#p=notjson", "%20%20", "d1:nope",
    "javascript:alert(1)", "<script>alert(1)</script>",
])
def test_decode_never_raises(raw):
    result = share.decode_document(raw)
    assert isinstance(result, dict)
    assert bool(result.get("error")) == share.is_decode_error(result)


@pytest.mark.parametrize("raw", ["", None, 5, {}, [], b"bytes"])
def test_decode_tolerates_non_string_input(raw):
    result = share.decode_document(raw)
    assert result["reason"] in share.DECODE_REASONS


def test_reason_covers_the_empty_payload_case():
    for raw in ("", "   ", "#p=", "#p=   "):
        assert share.decode_document(raw)["reason"] == "emptyPayload", raw


def test_reason_covers_a_truncated_link():
    url = share.encode_document(SOURCE, name=NAME)["url"]
    token = share.fragment_of(url)
    # cut the token short mid-payload
    short = token[: max(1, len(token) // 2)]
    result = share.decode_document(share.URL_PREFIX + short)
    assert result["reason"] in ("truncated", "malformed")
    assert result["error"] is True


def test_reason_covers_an_unsupported_version():
    body = json.dumps({"v": 2, "s": SOURCE, "k": share.make_knobs()})
    result = share.decode_document("#p=" + share._compress(body))
    assert result["reason"] == "unsupportedVersion"
    assert result["error"] is True


def test_mandatory_version_rejects_payloads_without_a_version():
    body = json.dumps({"s": SOURCE})
    result = share.decode_document("#p=" + share._compress(body))
    assert result["reason"] in ("unsupportedVersion", "malformed")


def test_reason_covers_random_text_with_a_valid_prefix():
    result = share.decode_document("#p=totally-not-encoded-🚫")
    assert result["reason"] in ("malformed", "truncated")


def test_every_reason_has_a_message_and_a_dismissal_path():
    assert set(share.DECODE_REASONS) == {"malformed", "unsupportedVersion",
                                         "truncated", "emptyPayload"}
    for reason in share.DECODE_REASONS:
        error = share.decode_error(reason)
        assert error["error"] is True
        assert error["reason"] == reason
        assert len(error["message"]) > 20
        assert error["action"]


def test_compression_is_required_and_effective():
    source = "flowchart TD\n" + "  same[label] --> same\n" * 300
    body = json.dumps(share.payload_from_document(source))
    token = share._compress(body)
    assert len(token) < len(body)          # compressed before encoding
    assert share.decode_document("#p=" + token)["s"] == source
