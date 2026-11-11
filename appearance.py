"""appearance.py — the single appearance resolver (contracts/appearance-contract.md).

Pure Python, standard library only. Turns AppearanceKnobs plus a diagramType
into one deterministic, JSON-serialisable ResolvedAppearance consumed, as the
same object, by the preview, the exporters and the shared link (FR-008 / A-2).

Numeric contracts asserted by tests/test_appearance.py:
  * text multipliers 0.75 / 0.9 / 1.0 / 1.25 / 1.75 on a 16 px basis;
    largest / smallest == 2.3333 which is >= the 2.0 minimum (A-3)
  * density multipliers: compact 0.85/0.85/0.9, normal 1.0/1.0/1.0,
    roomy (default) 1.25/1.2/1.1, open 1.5/1.4/1.2 (section 4)
  * contrast invariant: text-vs-fill >= 4.5:1, line-vs-panel >= 3:1, measured
    with sRGB relative luminance; offenders are clamped AND reported (A-4)
  * precedence sourceOf: frontmatter > knobs > defaults (A-5, section 7)
  * section 6 frozen settings present in every resolved output (A-7)
  * derived colours come from baseColors plus the fixed mix table only (A-6)
"""

import copy
import json

# ---------------------------------------------------------------------------
# 1. Knob domains (pinned in data-model section 4a)
# ---------------------------------------------------------------------------

# The offered scheme list. It is exactly the key set of ``SCHEMES`` below --
# one source of truth, asserted in tests/test_appearance.py, because the two
# lists drifting was a real bug: ``dark`` lived in ``SCHEMES`` only, so the knob
# ``schemeName="dark"`` failed domain validation and the resolver quietly drew a
# ``neo`` page instead of a dark one. ``dark`` is a verified Mermaid theme name
# (research R-2), so it is offered; appending it last also keeps every numeric
# index of this domain (share links may carry ``schemeName: 3``) unchanged.
SCHEME_NAMES = (
    "neo", "neo-dark", "redux", "redux-dark", "redux-color", "redux-dark-color",
    "default", "neutral", "forest", "base", "dark",
)
TEXT_SCALES = ("smallest", "small", "medium", "large", "largest")
FONT_FAMILIES = ("sans", "serif", "mono")
DENSITIES = ("compact", "normal", "roomy", "open")
PATH_EMPHASES = ("off", "soft", "strong")
EXPORT_SCALES = ("screen", "high", "print")
DIAGRAM_TYPES = ("flowchart", "sequence", "class", "state", "er", "gantt",
                 "pie", "journey", "mindmap")

DEFAULT_KNOBS = {
    "schemeName": "neo",
    "baseColors": None,
    "textScale": "medium",
    "fontFamily": "sans",
    "density": "roomy",
    "pathEmphasis": "soft",
    "exportScale": "high",
    "exportBackground": "white",
}
KNOB_DOMAINS = {
    "schemeName": SCHEME_NAMES,
    "textScale": TEXT_SCALES,
    "fontFamily": FONT_FAMILIES,
    "density": DENSITIES,
    "pathEmphasis": PATH_EMPHASES,
    "exportScale": EXPORT_SCALES,
}
# exportBackground accepts the two words or a #rrggbb custom value (FR-029).
EXPORT_BACKGROUND_WORDS = ("white", "transparent")
EXPORT_SCALE_MULTIPLIERS = {"screen": 2, "high": 3, "print": 4}
# A-9: print/screen raster dimension ratio == 4 / 2 == 2.0 exactly.
PRINT_VS_SCREEN_RATIO = (EXPORT_SCALE_MULTIPLIERS["print"]
                         / EXPORT_SCALE_MULTIPLIERS["screen"])

# ---------------------------------------------------------------------------
# 3. Text size multipliers (basis 16 px == today's look, FR-001)
# ---------------------------------------------------------------------------

TEXT_SCALE_MULTIPLIERS = {
    "smallest": 0.75,
    "small": 0.9,
    "medium": 1.0,
    "large": 1.25,
    "largest": 1.75,
}
TEXT_SIZE_BASIS_PX = 16
TEXT_SIZE_RATIO_MIN = 2.0
# A-3: 1.75 / 0.75 == 2.3333...
TEXT_SIZE_RATIO = (TEXT_SCALE_MULTIPLIERS["largest"]
                   / TEXT_SCALE_MULTIPLIERS["smallest"])

# ---------------------------------------------------------------------------
# 4. Spacing multipliers (FR-006)
# ---------------------------------------------------------------------------

DENSITY_MULTIPLIERS = {
    # density -> (nodeSpacing x, rankSpacing x, padding x)
    "compact": (0.85, 0.85, 0.9),
    "normal": (1.0, 1.0, 1.0),
    "roomy": (1.25, 1.2, 1.1),
    "open": (1.5, 1.4, 1.2),
}

# ---------------------------------------------------------------------------
# FR-005: web-safe stacks only (research R-2 — a web font would not embed in
# the exported SVG, so preview and export would diverge).
# ---------------------------------------------------------------------------

FONT_STACKS = {
    "sans": '"trebuchet ms", verdana, arial, sans-serif',
    "serif": 'Georgia, "Times New Roman", serif',
    "mono": "ui-monospace, Consolas, Menlo, 'Courier New', monospace",
}

# ---------------------------------------------------------------------------
# 5. Named schemes (10 offered, >= 6 required). Each key is a verified Mermaid
# theme name (research R-2) carrying an explicit themeVariables overlay.
# ``background`` is the panel colour the line-vs-panel half is measured on.
# Light, dark and a high-contrast entry are all covered (FR-003).
# ---------------------------------------------------------------------------

_LIGHT_VARS = {
    "primaryColor": "#e2eef9",
    "primaryBorderColor": "#2f4b8f",
    "lineColor": "#555b6e",
    "secondaryColor": "#d4f0dd",
    "tertiaryColor": "#f0f0f0",
    "edgeLabelBackground": "#f0f0f0",
    "clusterBkg": "#f2f4f9",
    "clusterBorder": "#5f6673",
}
_DARK_VARS = {
    "primaryColor": "#24294f",
    "primaryBorderColor": "#8a93cf",
    "lineColor": "#a6aed6",
    "secondaryColor": "#1f3a34",
    "tertiaryColor": "#333966",
    "edgeLabelBackground": "#333966",
    "clusterBkg": "#20243f",
    "clusterBorder": "#7f86a8",
}

SCHEMES = {
    "default": {
        "label": "Mermaid default",
        "theme": "default", "background": "#ffffff", "textColor": "#181e45",
        "variables": dict(_LIGHT_VARS),
    },
    "neutral": {
        "label": "Neutral (high contrast)",
        "theme": "neutral", "background": "#ffffff", "textColor": "#1a1a1a",
        "variables": {**_LIGHT_VARS, "primaryColor": "#e6e6e6",
                      "secondaryColor": "#dedede", "tertiaryColor": "#d9d9d9",
                      "edgeLabelBackground": "#d9d9d9", "clusterBkg": "#ebebeb",
                      "lineColor": "#4a4a4a", "primaryBorderColor": "#3d3d3d",
                      "clusterBorder": "#545454"},
    },
    "forest": {
        "label": "Forest",
        "theme": "forest", "background": "#ffffff", "textColor": "#1a2a1a",
        "variables": {**_LIGHT_VARS, "primaryColor": "#ece7dd",
                      "secondaryColor": "#eeeec2",
                      "primaryBorderColor": "#006d32", "lineColor": "#707070",
                      "tertiaryColor": "#eef4f4",
                      "edgeLabelBackground": "#eef4f4",
                      "clusterBkg": "#e8ede8", "clusterBorder": "#006d32"},
    },
    "base": {
        "label": "Base",
        "theme": "base", "background": "#ffffff", "textColor": "#1f2d3d",
        "variables": dict(_LIGHT_VARS),
    },
    "neo": {
        "label": "Neo (light)",
        "theme": "neo", "background": "#ffffff", "textColor": "#333333",
        "variables": {**_LIGHT_VARS, "primaryColor": "#eff6ff",
                      "primaryBorderColor": "#3b5bdb", "lineColor": "#8d8d8d",
                      "clusterBorder": "#545454"},
    },
    "dark": {
        "label": "Mermaid dark",
        "theme": "dark", "background": "#1f1f1f", "textColor": "#e8e6e3",
        "variables": {**_DARK_VARS, "primaryColor": "#3f51b5",
                      "primaryBorderColor": "#a3a3a3", "lineColor": "#e8e8e8",
                      "tertiaryColor": "#4a4a4a",
                      "edgeLabelBackground": "#4a4a4a",
                      "clusterBkg": "#2f2f2f", "clusterBorder": "#cfcfcf",
                      "secondaryColor": "#37474f"},
    },
    "neo-dark": {
        "label": "Neo dark",
        "theme": "neo-dark", "background": "#1a1b26", "textColor": "#c0caf5",
        "variables": dict(_DARK_VARS),
    },
    "redux": {
        "label": "Redux",
        "theme": "redux", "background": "#ffffff", "textColor": "#2f3b52",
        "variables": {**_LIGHT_VARS, "primaryColor": "#eef2ff",
                      "primaryBorderColor": "#3f51b5", "lineColor": "#626675"},
    },
    "redux-dark": {
        "label": "Redux dark",
        "theme": "redux-dark", "background": "#202124", "textColor": "#e8eaed",
        "variables": {**_DARK_VARS, "primaryColor": "#37474f",
                      "primaryBorderColor": "#b0bec5", "lineColor": "#cfd8dc",
                      "tertiaryColor": "#455a64",
                      "edgeLabelBackground": "#455a64",
                      "clusterBkg": "#37474f", "clusterBorder": "#b0bec5",
                      "secondaryColor": "#455a64"},
    },
    "redux-color": {
        "label": "Redux colour",
        "theme": "redux-color", "background": "#ffffff", "textColor": "#333447",
        "variables": {**_LIGHT_VARS, "primaryColor": "#e6d7f9",
                      "secondaryColor": "#c8e6c9",
                      "primaryBorderColor": "#6a3fb5", "lineColor": "#626675"},
    },
    "redux-dark-color": {
        "label": "Redux dark colour",
        "theme": "redux-dark-color", "background": "#202124",
        "textColor": "#eae4f7",
        "variables": {**_DARK_VARS, "primaryColor": "#4527a0",
                      "primaryBorderColor": "#b39ddb", "lineColor": "#d9c8ee",
                      "tertiaryColor": "#4527a0",
                      "edgeLabelBackground": "#4527a0",
                      "clusterBkg": "#4527a0", "clusterBorder": "#b39ddb",
                      "secondaryColor": "#3949ab"},
    },
}
# The ten offered knob names above are the domain; "neutral" is the FR-003
# high-contrast entry (near-black ink and rules on a white panel).

# ---------------------------------------------------------------------------
# Derived-colour mode (FR-004 / A-6): fixed mixes of foreground INTO background
# mirroring the two-colour foundation pattern. Percent == foreground weight.
# The contract's ten mixes, plus aliases that re-use a mix for a second
# mermaid variable; no colour outside {background, foreground} + constants.
# ---------------------------------------------------------------------------

BASE_COLOR_MIXES = {
    "textColor": 100,            # text 100 %
    "secondaryTextColor": 60,    # secondary text 60 %
    "edgeLabelTextColor": 40,    # edge label 40 %
    "faintColor": 25,            # faint 25 %
    "lineColor": 50,             # connectors 50 %
    "arrowHeadColor": 85,        # arrowheads 85 %
    "primaryColor": 3,           # node fill 3 %
    "clusterBkg": 5,             # group header 5 %
    "tertiaryColor": 12,         # inner stroke 12 %
    "primaryBorderColor": 20,    # node stroke 20 %
    # aliases (same fixed mixes, second mermaid variable names)
    "edgeLabelBackground": 25,   # faint tone doubles as the edge-label plate
    "secondaryColor": 3,         # secondary fills use the node fill mix
    "clusterBorder": 20,         # cluster stroke doubles as the node stroke
}

# ---------------------------------------------------------------------------
# FR-007 path emphasis: edge stroke width (+ a stronger edge colour in scheme
# mode only, so derived mode keeps its two-input guarantee, A-6).
# ---------------------------------------------------------------------------

PATH_EMPHASIS_STROKE_WIDTH = {"off": 1, "soft": 2, "strong": 3}
PATH_EMPHASIS_STRONG_BORDER = {"light": "#2f4b8f", "dark": "#d5dcff"}

# ---------------------------------------------------------------------------
# Contrast invariant (FR-011 / A-4). sRGB relative luminance, WCAG 2.x ratio.
# ---------------------------------------------------------------------------

TEXT_VS_FILL_MIN = 4.5
LINE_VS_PANEL_MIN = 3.0
# Extra margin reported above the floor, so the offered stock schemes never
# clamp at all (contract section 5: exhaustive check yields zero clamps).
_CONTRAST_REPORT_MARGIN = 0.006
# text variable -> fill variables it can be drawn on (the "text-vs-fill" half)
_TEXT_ON_FILLS = ("primaryColor", "secondaryColor", "tertiaryColor",
                  "clusterBkg", "edgeLabelBackground", "faintColor")
TEXT_FILL_PAIRS = (
    ("textColor", _TEXT_ON_FILLS),
    ("secondaryTextColor", ("primaryColor", "clusterBkg")),
    ("edgeLabelTextColor", ("edgeLabelBackground", "faintColor", "primaryColor")),
)
# line variables checked against the panel (the "line-vs-panel" half)
LINE_PANEL_VARS = ("lineColor", "primaryBorderColor", "clusterBorder",
                   "arrowHeadColor", "defaultLinkColor", "signalColor",
                   "nodeBorder", "actorBorder", "tertiaryBorderColor",
                   "secondaryBorderColor")

# ---------------------------------------------------------------------------
# Which spelling Mermaid actually reads
#
# Measured in Chromium (mermaid 11.12.0): under every *named* theme the only
# computed colours that followed our palette were the node fill and the node
# border. Link/arrow stroke stayed on the stock #9370DB, the edge-label plate on
# the stock #ECECFF and label text on the stock text colour, even though
# `themeVariables.lineColor` / `edgeLabelBackground` / `textColor` were all
# present in the initialize object. The reason is in Mermaid's own theming docs:
# its CSS is generated from the *derived* variable names, which the theme engine
# computes itself -- `nodeTextColor <- primaryTextColor`,
# `titleColor <- tertiaryTextColor`, `defaultLinkColor <- lineColor`,
# `clusterBorder <- tertiaryBorderColor`, `nodeBorder <- primaryBorderColor`,
# `actorTextColor <- primaryTextColor`, and `edgeLabelBackground` is
# "calculated from secondaryColor". A base key alone therefore changes two
# elements and leaves three pinned to library stock: exactly what FR-003/A-6
# calls a half-styled diagram. The resolver emits the derived spelling too, from
# the palette's own value (same colour, the name the renderer reads), so no CSS
# injection and no third input to the two-colour derivation is needed.
# ---------------------------------------------------------------------------
PALETTE_ALIASES = {
    # label / title / note text -> the palette's text colour (text is 100 %)
    "primaryTextColor": "textColor",
    "secondaryTextColor": "textColor",
    "tertiaryTextColor": "textColor",
    "nodeTextColor": "textColor",
    "titleColor": "textColor",
    "actorTextColor": "textColor",
    "classText": "textColor",
    "noteTextColor": "textColor",
    "edgeLabelTextColor": "textColor",
    # lines / arrows / signal lines -> the palette's line colour
    "defaultLinkColor": "lineColor",
    "signalColor": "lineColor",
    "actorLineColor": "lineColor",
    # strokes -> the palette's node stroke
    "nodeBorder": "primaryBorderColor",
    "actorBorder": "primaryBorderColor",
    "tertiaryBorderColor": "primaryBorderColor",
    "secondaryBorderColor": "primaryBorderColor",
    "noteBorderColor": "primaryBorderColor",
    # plates -> the palette's edge-label plate
    "noteBkgColor": "edgeLabelBackground",
    "labelBoxBkgColor": "edgeLabelBackground",
}


def apply_palette_aliases(variables):
    """Fill Mermaid's derived variable spellings from this palette's own values.

    ``setdefault`` semantics: a value the scheme authored, the two-colour mixes
    produced, or the user's diagram text supplied for that exact key always
    wins -- this only adds the names that were absent. Idempotent.
    """
    for alias, source in PALETTE_ALIASES.items():
        value = variables.get(source)
        if alias not in variables and isinstance(value, str) and value:
            variables[alias] = value
    return variables
# Every derived text spelling above is registered against the same fills as its
# source, so a palette cannot keep a label readable and let an aliased spelling
# (which is the name the renderer reads) go under the floor unchecked. They
# start out equal in value, so the named schemes stay clamp-free.
TEXT_FILL_PAIRS = TEXT_FILL_PAIRS + tuple(
    (alias, _TEXT_ON_FILLS)
    for alias, source in PALETTE_ALIASES.items()
    if source == "textColor" and alias != "secondaryTextColor"
    and alias != "edgeLabelTextColor")


# ---------------------------------------------------------------------------
# Text size: the spelling that reaches a label.
#
# Measured in the same Chromium run: `%%themeVariables.fontSize: "28px"` is the
# key that changes a rendered flowchart label (16 -> 28 px). The top-level
# numeric ``fontSize`` is NOT it -- it becomes Mermaid's derived *base* (28 in,
# 14 px on the label), and unit-less or differently-spelled variants such as
# ``primaryFontSize`` are accepted by the config type but never applied. The
# numeric top-level value stays (contract section 3 documents it, and the
# per-diagram ``fontSize`` keys consume it), and the px string is emitted
# alongside it in ``themeVariables``. The 2.0x largest/smallest ratio of section
# 3 is preserved by construction: 28px / 12px = 2.333x, identical to 28 / 12.
# ---------------------------------------------------------------------------
THEME_FONT_SIZE_KEY = "fontSize"

# Exact px strings for the five sizes of section 3, kept next to the test that
# pins them (16 px basis, half-up rounding -- the same arithmetic as the
# integer ``fontSize`` output).
TEXT_SIZE_PX = {
    "smallest": "12px",      # 16 * 0.75
    "small": "14px",         # 16 * 0.9  = 14.4 -> 14
    "medium": "16px",        # 16
    "large": "20px",         # 16 * 1.25
    "largest": "28px",       # 16 * 1.75
}

# ---------------------------------------------------------------------------
# Section 6: frozen (non-knob) settings, present in every resolved output.
# ---------------------------------------------------------------------------

FROZEN_SETTINGS = {
    "htmlLabels": False,
    "useHtmlLabels": False,
    "suppressErrorRendering": True,
    "securityLevel": "strict",
    "startOnLoad": False,
}
# Section 3 guard: these must never appear anywhere in the output.
FORBIDDEN_KEYS = ("wordWrap", "useMaxWidth", "wrap")

# ---------------------------------------------------------------------------
# Render ceilings the library enforces on its own input. Mermaid's documented
# defaults are ``maxEdges: 500`` and ``maxTextSize: 50000``; both reject the
# largest diagrams this app ships examples and fixtures for (the 50 000-char
# fixture has 1 265 edges), which would contradict SC-003's "a big diagram is
# never called broken". They live here because Mermaid only honours them on the
# ``mermaid.initialize()`` object — ``maxEdges``/``maxTextSize`` are *secure*
# settings, so a diagram's own ``%%{init}%%`` block cannot set or lower them.
# That is the library's documented security behaviour, not a relaxation of
# ``securityLevel: "strict"``: the values are constant per build and diagram
# text can never raise or lower them.
# ---------------------------------------------------------------------------

RENDER_LIMITS = {
    "maxEdges": 5000,
    "maxTextSize": 200000,
}
MERMAID_DEFAULT_RENDER_LIMITS = {"maxEdges": 500, "maxTextSize": 50000}

# ---------------------------------------------------------------------------
# Per-diagram families (stage C routing). ``keys`` is the ONLY set a family may
# emit — documented mermaid@11 config keys (research R-2), so an unknown key
# for that family can never appear. ``stock`` holds the library's own values,
# which is what ``normal`` density leaves in force. ``spacing`` maps an emitted
# key to the multiplier axis driving it (sequence uses its own messageMargin);
# ``text_keys`` receive the sized font — only types whose config defines its
# own fontSize (contract section 3).
# ---------------------------------------------------------------------------

# The emitted key set per family is exactly what the contract documents:
# section 4 names nodeSpacing / rankSpacing / padding (flowchart), padding as the
# nearest equivalent for mindmap, class and state, messageMargin for sequence;
# section 3 names a per-diagram fontSize for sequence, gantt, journey, mindmap
# and pie only. Keys the contract does not name (barHeight, boxMargin,
# noteMargin, er diagramPadding, ...) are never emitted, so the routing guard
# holds: an unlisted key cannot appear for a family.
DIAGRAM_FAMILIES = {
    "flowchart": {
        "keys": ("nodeSpacing", "rankSpacing", "padding"),
        # mermaid@11 documented flowchart defaults (config.type FlowchartDiagramConfig)
        "stock": {"nodeSpacing": 50, "rankSpacing": 50, "padding": 15},
        "spacing": {"nodeSpacing": "nodeSpacing", "rankSpacing": "rankSpacing",
                    "padding": "padding"},
        "text_keys": (),
    },
    "sequence": {
        "keys": ("messageMargin", "fontSize"),
        "stock": {"messageMargin": 40},
        "spacing": {"messageMargin": "rankSpacing"},
        "text_keys": ("fontSize",),
    },
    "class": {
        "keys": ("padding",),
        "stock": {"padding": 15},
        "spacing": {"padding": "padding"},
        "text_keys": (),
    },
    "state": {
        "keys": ("padding",),
        "stock": {"padding": 15},
        "spacing": {"padding": "padding"},
        "text_keys": (),
    },
    "er": {
        "keys": (),
        "stock": {},
        "spacing": {},
        "text_keys": (),
    },
    "journey": {
        "keys": ("fontSize",),
        "stock": {},
        "spacing": {},
        "text_keys": ("fontSize",),
    },
    "gantt": {
        "keys": ("fontSize",),
        "stock": {},
        "spacing": {},
        "text_keys": ("fontSize",),
    },
    "pie": {
        "keys": ("fontSize",),
        "stock": {},
        "spacing": {},
        "text_keys": ("fontSize",),
    },
    "mindmap": {
        "keys": ("padding", "fontSize"),
        "stock": {"padding": 5},
        "spacing": {"padding": "padding"},
        "text_keys": ("fontSize",),
    },
}
TYPE_TO_FAMILY = {name: name for name in DIAGRAM_FAMILIES}


# ---------------------------------------------------------------------------
# Colour maths (sRGB relative luminance per WCAG 2.x)
# ---------------------------------------------------------------------------

def _srgb_channel(value_8bit):
    v = value_8bit / 255.0
    if v <= 0.04045:
        return v / 12.92
    return ((v + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color):
    """sRGB relative luminance of #rrggbb — the FR-011 measurement basis."""
    r, g, b = hex_to_rgb(hex_color)
    return (0.2126 * _srgb_channel(r) + 0.7152 * _srgb_channel(g)
            + 0.0722 * _srgb_channel(b))


def contrast_ratio(hex_a, hex_b):
    """WCAG contrast ratio between two #rrggbb colours."""
    lum_a = relative_luminance(hex_a)
    lum_b = relative_luminance(hex_b)
    hi, lo = max(lum_a, lum_b), min(lum_a, lum_b)
    return (hi + 0.05) / (lo + 0.05)


def is_hex_color(value):
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        return False
    return all(c in "0123456789abcdefABCDEF" for c in value[1:])


def hex_to_rgb(hex_color):
    if not is_hex_color(hex_color):
        raise ValueError("not a #rrggbb colour: %r" % (hex_color,))
    return (int(hex_color[1:3], 16), int(hex_color[3:5], 16),
            int(hex_color[5:7], 16))


def _rgb_to_hex(rgb_iterable):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c))))
                                   for c in rgb_iterable)


def mix_colors(background_hex, foreground_hex, foreground_percent):
    """Mix foreground INTO background at foreground_percent (A-6 primitive)."""
    weight = foreground_percent / 100.0
    bg = hex_to_rgb(background_hex)
    fg = hex_to_rgb(foreground_hex)
    return _rgb_to_hex(b + (f - b) * weight for b, f in zip(bg, fg))


# ---------------------------------------------------------------------------
# Knob sanitising
# ---------------------------------------------------------------------------

def valid_knobs(knobs):
    """Keep only in-domain values; unknown names/values are dropped, never raise."""
    clean = {}
    if not isinstance(knobs, dict):
        return clean
    for name, domain in KNOB_DOMAINS.items():
        if name in knobs and knobs[name] in domain:
            clean[name] = knobs[name]
    if "baseColors" in knobs:
        base = knobs["baseColors"]
        if base is None:
            clean["baseColors"] = None
        elif isinstance(base, dict):
            bg, fg = base.get("background"), base.get("foreground")
            if is_hex_color(bg) and is_hex_color(fg):
                clean["baseColors"] = {"background": bg.lower(),
                                       "foreground": fg.lower()}
    if "exportBackground" in knobs:
        background = knobs["exportBackground"]
        if background in EXPORT_BACKGROUND_WORDS or is_hex_color(background):
            clean["exportBackground"] = (background.lower()
                                         if isinstance(background, str)
                                         else background)
    return clean


def _scale(stock_value, multiplier):
    """Round-half-up scaling so the tables in section 4 stay predictable."""
    scaled = stock_value * multiplier
    floor = int(scaled)
    return floor + 1 if (scaled - floor) >= 0.5 else floor


def _knob(clean, name):
    """(value, source) across contract section 7 layers 2 and 3."""
    if name in clean:
        return clean[name], "knob"
    return DEFAULT_KNOBS[name], "default"


# ---------------------------------------------------------------------------
# Contrast enforcement (clamp-and-report)
# ---------------------------------------------------------------------------

def _blend_toward(start_hex, end_hex, weight):
    start = hex_to_rgb(start_hex)
    end = hex_to_rgb(end_hex)
    return _rgb_to_hex(s + (e - s) * weight for s, e in zip(start, end))


def _endpoints_away_from(panel):
    """Blend targets ordered by how far they sit from the panel luminance.

    Clamping pushes a colour toward the endpoint that moves it *away* from the
    panel, which is where every derived fill already sits, so the search always
    converges for the two-colour mode.
    """
    panel_lum = relative_luminance(panel)
    return sorted(("#ffffff", "#000000"),
                  key=lambda e: -abs(relative_luminance(e) - panel_lum))


def _clamp_variable(color, constraints, panel):
    """Single blend from ``color`` satisfying every (reference, floor) pair.

    Returns ``(value, clamped)``. One blend only — no chained pushes — so the
    result is always still a mix of the two base colours plus an endpoint,
    which is what keeps A-6 true while the invariant holds.
    """
    limits = [(ref, floor) for ref, floor in constraints
              if isinstance(ref, str) and is_hex_color(ref)]
    if not limits:
        return color, False
    if all(contrast_ratio(color, ref) >= floor + _CONTRAST_REPORT_MARGIN
           for ref, floor in limits):
        return color, False
    for step in range(1, 81):
        weight = step / 80.0
        for endpoint in _endpoints_away_from(panel):
            candidate = _blend_toward(color, endpoint, weight)
            if all(contrast_ratio(candidate, ref) >= floor
                   for ref, floor in limits):
                return candidate, candidate != color
    return _blend_toward(color, _endpoints_away_from(panel)[0], 1.0), True


def contrast_constraints(variables, panel):
    """Ordered {variable: [(referenceValue, minimumRatio)]} invariant table."""
    limits = {}
    for text_key, fill_keys in TEXT_FILL_PAIRS:
        limits.setdefault(text_key, []).extend(
            (fill_key, TEXT_VS_FILL_MIN) for fill_key in fill_keys)
    for line_key in LINE_PANEL_VARS:
        limits.setdefault(line_key, []).append(("panel", LINE_VS_PANEL_MIN))
    return limits


def derived_colour_set(background, foreground):
    """Every colour derived mode can emit: the fixed mixes, plus any blend of
    one of them toward an endpoint (the clamp path of stage B, FR-011)."""
    values = set()
    for percent in BASE_COLOR_MIXES.values():
        raw = mix_colors(background, foreground, percent)
        values.add(raw)
        for endpoint in ("#ffffff", "#000000"):
            for step in range(1, 81):
                values.add(_blend_toward(raw, endpoint, step / 80.0))
    return values


def _enforce_contrast(variables, panel, protected=()):
    """Apply the invariant in place; return the ordered list of clamped names.

    ``protected`` names variables supplied by the user's own diagram text: their
    value wins (section 7) so they are reported through ``frontmatterColorKeys``
    instead of rewritten. Fills and the panel are never rewritten - only the
    text and line variables, "the offending variable" of contract section 5.
    """
    clamped = []
    for name, pairs in contrast_constraints(variables, panel).items():
        color = variables.get(name)
        if not (isinstance(color, str) and is_hex_color(color)):
            continue
        limits = []
        for ref_key, floor in pairs:
            ref = panel if ref_key == "panel" else variables.get(ref_key)
            if isinstance(ref, str) and is_hex_color(ref):
                limits.append((ref, floor))
        value, changed = _clamp_variable(color, limits, panel)
        variables[name] = value
        if changed and name not in protected and name not in clamped:
            clamped.append(name)
    return [name for name in clamped if name not in protected]



def contrast_pairs(variables, panel=None):
    """Every invariant pair of a colour set: (name, ratio, floor, variable).

    The conformance suite re-derives these independently of the resolver's own
    bookkeeping, which is what makes "zero unreported clamps" checkable (A-4).
    """
    panel = panel if panel is not None else variables.get("background")
    pairs = []
    for text_key, fill_keys in TEXT_FILL_PAIRS:
        text = variables.get(text_key)
        if isinstance(text, str) and is_hex_color(text):
            for fill_key in fill_keys:
                fill = variables.get(fill_key)
                if isinstance(fill, str) and is_hex_color(fill):
                    pairs.append(("%s on %s" % (text_key, fill_key),
                                  contrast_ratio(text, fill), TEXT_VS_FILL_MIN,
                                  text_key))
    if isinstance(panel, str) and is_hex_color(panel):
        for line_key in LINE_PANEL_VARS:
            line = variables.get(line_key)
            if isinstance(line, str) and is_hex_color(line):
                pairs.append(("%s on panel" % line_key,
                              contrast_ratio(line, panel), LINE_VS_PANEL_MIN,
                              line_key))
    return pairs


def stock_combinations():
    """Every combination reachable through the offered scheme knobs (named
    scheme mode: no baseColors derivation)."""
    combos = []
    for scheme in SCHEME_NAMES:
        for text_scale in TEXT_SCALES:
            for density in DENSITIES:
                for emphasis in PATH_EMPHASES:
                    combos.append({"schemeName": scheme, "baseColors": None,
                                   "textScale": text_scale,
                                   "fontFamily": "sans", "density": density,
                                   "pathEmphasis": emphasis})
    return combos


# ---------------------------------------------------------------------------
# Resolution: stage A (knob defaults) -> stage B (colour + clamp) ->
# stage C (per-diagram spacing routing)
# ---------------------------------------------------------------------------

def _scheme_variables(scheme):
    variables = {"background": scheme["background"],
                 "textColor": scheme["textColor"]}
    variables.update(scheme["variables"])
    variables["background"] = scheme["background"]
    variables["textColor"] = scheme["textColor"]
    return variables


def parse_px_size(value):
    """Front-matter text size -> integer px, or None when it does not name one.

    Mermaid accepts the size bare (`fontSize: 28`) and with a unit
    (`fontSize: "28px"`), in either the flat config or `themeVariables`; the
    resolver normalises all four spellings to one integer. Anything else (a
    relative `em`, garbage, a boolean) is not a size this app understands, so it
    is reported as absent and the knob layer decides.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(round(value))
    if isinstance(value, str):
        text = value.strip().lower()
        if text.endswith("px"):
            text = text[:-2].strip()
        try:
            return int(round(float(text)))
        except ValueError:
            return None
    return None


def frontmatter_font_size(fm):
    """(px, verbatim_spelling) from ``fontSize`` / ``themeVariables.fontSize``.

    ``verbatim_spelling`` is what the user wrote when it already carried a unit;
    None means the resolver should spell it itself as ``"<px>px"``.
    """
    for source in (fm.get("fontSize"),
                   fm.get("themeVariables", {}).get("fontSize")
                   if isinstance(fm.get("themeVariables"), dict) else None):
        px = parse_px_size(source)
        if px is not None:
            return px, (source if isinstance(source, str) else None)
    return None, None


def resolve(knobs, diagram_type, frontmatter=None):
    """AppearanceKnobs + diagram type -> ResolvedAppearance (contract 1 and 2).

    ``frontmatter`` is the parsed config dict the caller read from
    ``ParseResult`` (%%{init}%% or YAML front-matter); the keys it names win
    over knobs (section 7: frontmatter > knobs > defaults). The result is
    JSON-serialisable and deterministic — equal inputs give deep-equal outputs
    (A-1) — and carries the ``clamped`` / ``sourceOf`` report fields plus the
    section 6 ``frozen`` settings.

    Text size, as measured in Chromium with mermaid 11.12.0: the key that
    actually changes a rendered flowchart label is
    ``themeVariables.fontSize`` as a **string with a px unit**, so this emits it
    (alongside the numeric ``fontSize`` contract section 3 documents, which
    Mermaid only turns into its derived base: 28 in -> 14 px on the label).
    ``primaryFontSize`` and friends are accepted by Mermaid's config type but do
    NOT size flowchart labels in 11.12 -- ``themeVariables.fontSize`` is the
    operative key, and a size named by the user's own diagram text is passed
    through with the user's own spelling (``sourceOf.textScale == "frontmatter"``).

    Colours likewise carry Mermaid's *derived* spellings
    (``PALETTE_ALIASES``: ``nodeTextColor``/``primaryTextColor``,
    ``defaultLinkColor``, ``nodeBorder``/``tertiaryBorderColor``,
    ``titleColor``), because that is what its generated CSS reads: setting only
    the base keys left link stroke, edge-label plate and label text on Mermaid's
    stock values while just the node fill and border followed the scheme.
    """
    # ---------------- stage A: knob values and their layer ----------------
    clean = valid_knobs(knobs)
    fm = frontmatter if isinstance(frontmatter, dict) else {}

    scheme_value, scheme_source = _knob(clean, "schemeName")
    text_value, text_source = _knob(clean, "textScale")
    font_value, font_source = _knob(clean, "fontFamily")
    density_value, density_source = _knob(clean, "density")
    emphasis_value, emphasis_source = _knob(clean, "pathEmphasis")
    base_colors, base_source = _knob(clean, "baseColors")
    export_scale_name, export_scale_source = _knob(clean, "exportScale")
    export_bg_name, export_bg_source = _knob(clean, "exportBackground")

    family_name = TYPE_TO_FAMILY.get(diagram_type, "flowchart")
    family = DIAGRAM_FAMILIES[family_name]
    fm_family = fm.get(family_name) if isinstance(fm.get(family_name), dict) else {}
    fm_text_px, fm_text_spelling = frontmatter_font_size(fm)
    fm_sets_text = fm_text_px is not None
    fm_sets_font = isinstance(fm.get("fontFamily"), str) and bool(fm.get("fontFamily"))
    fm_sets_spacing = any(key in fm_family for key in family["spacing"])

    # ---------------- stage B: colour derivation, clamp, report -----------
    derived = base_colors is not None
    scheme = SCHEMES.get(scheme_value, SCHEMES[DEFAULT_KNOBS["schemeName"]])
    theme_family = scheme["theme"]
    panel = scheme["background"]
    variables = _scheme_variables(scheme)

    if derived:
        bg = base_colors["background"]
        fg = base_colors["foreground"]
        panel = bg
        variables = {"background": bg}
        for name, percent in BASE_COLOR_MIXES.items():
            variables[name] = mix_colors(bg, fg, percent)
        theme_family = "base" if relative_luminance(bg) >= 0.5 else "dark"

    # FR-007 emphasis: edge stroke width always, edge colour only in scheme
    # mode (a derived-mode colour change would add a third input, breaking A-6)
    variables["lineStrokeWidth"] = PATH_EMPHASIS_STROKE_WIDTH[emphasis_value]
    if emphasis_value == "strong" and not derived:
        side = "dark" if relative_luminance(panel) < 0.5 else "light"
        variables["primaryBorderColor"] = PATH_EMPHASIS_STRONG_BORDER[side]

    # section 7 layer 1: front-matter wins for the keys it names
    fm_protected = set()
    fm_theme = fm.get("theme")
    if isinstance(fm_theme, str) and fm_theme in SCHEMES:
        scheme_source = "frontmatter"
        theme_family = SCHEMES[fm_theme]["theme"]
        panel = SCHEMES[fm_theme]["background"]
        variables = _scheme_variables(SCHEMES[fm_theme])
        variables["lineStrokeWidth"] = PATH_EMPHASIS_STROKE_WIDTH[emphasis_value]
        if emphasis_value == "strong" and not derived:
            side = "dark" if relative_luminance(panel) < 0.5 else "light"
            variables["primaryBorderColor"] = PATH_EMPHASIS_STRONG_BORDER[side]

    fm_vars = fm.get("themeVariables")
    if isinstance(fm_vars, dict):
        scheme_source = "frontmatter"
        if derived:
            base_source = "frontmatter"
        for key, value in fm_vars.items():
            if isinstance(key, str) and isinstance(value, str) and value:
                variables[key] = value
                fm_protected.add(key)
        if is_hex_color(fm_vars.get("background")):
            panel = fm_vars["background"]
    if is_hex_color(fm.get("lineColor")):
        variables["lineColor"] = fm["lineColor"]
        fm_protected.add("lineColor")

    # Mermaid's own CSS reads the derived spellings, not the base keys, so the
    # aliases go in *before* the invariant pass: an aliased spelling is then
    # clamped and reported exactly like the variable it mirrors.
    apply_palette_aliases(variables)
    clamped = _enforce_contrast(variables, panel, protected=fm_protected)

    if fm_sets_font:
        font_family = fm["fontFamily"]
    else:
        font_family = FONT_STACKS[font_value]
    if fm_sets_text:
        font_size = fm_text_px
    else:
        font_size = int(round(TEXT_SIZE_BASIS_PX
                              * TEXT_SCALE_MULTIPLIERS[text_value]))
    # THE operative text-size key (browser-measured, mermaid 11.12.0): the label
    # follows ``themeVariables.fontSize`` as a *unit-carrying string*. The
    # numeric top-level ``fontSize`` below only becomes Mermaid's derived base
    # (28 in -> 14 px on the label), and variants such as ``primaryFontSize``
    # are accepted by the config type but never applied -- neither sizes
    # flowchart labels in 11.12, so this string is what FR-002 rides on. A size
    # the user's own diagram text spelled out is passed through verbatim
    # (section 7: their value, their spelling); otherwise the resolved integer
    # is written with the px unit. Either way front matter wins over the scheme
    # palette and over the knob, and `sourceOf.textScale` says "frontmatter".
    variables[THEME_FONT_SIZE_KEY] = (fm_text_spelling if fm_sets_text
                                      and fm_text_spelling else
                                      "%dpx" % font_size)

    # ---------------- stage C: per-diagram spacing routing ----------------
    mult_node, mult_rank, mult_pad = DENSITY_MULTIPLIERS[density_value]
    axes = {"nodeSpacing": mult_node, "rankSpacing": mult_rank,
            "padding": mult_pad}
    diagram_cfg = {}
    for key, axis in family["spacing"].items():
        diagram_cfg[key] = _scale(family["stock"][key], axes[axis])
    for key in family["text_keys"]:
        diagram_cfg[key] = font_size
    for key, value in fm_family.items():
        if key in family["keys"]:
            diagram_cfg[key] = value
    if fm_sets_spacing:
        density_source = "frontmatter"

    per_diagram = {family_name: diagram_cfg}
    source_of = {
        "schemeName": scheme_source,
        "baseColors": "frontmatter" if (isinstance(fm_vars, dict) and derived)
        else base_source,
        "textScale": "frontmatter" if fm_sets_text else text_source,
        "fontFamily": "frontmatter" if fm_sets_font else font_source,
        "density": density_source,
        "pathEmphasis": emphasis_source,
        "exportScale": export_scale_source,
        "exportBackground": export_bg_source,
    }

    output = {
        # data-model section 5 authoritative keys
        "mermaidTheme": theme_family,
        "themeVariables": variables,
        "perDiagramConfig": per_diagram,
        "rasterScale": EXPORT_SCALE_MULTIPLIERS[export_scale_name],
        "rasterBackground": export_bg_name,
        # contract section 2 aliases (identical values, kept for consumers)
        "diagram_config": copy.deepcopy(per_diagram),
        "export": {
            "mermaidTheme": theme_family,
            "themeVariables": copy.deepcopy(variables),
            "perDiagramConfig": copy.deepcopy(per_diagram),
            "scale": EXPORT_SCALE_MULTIPLIERS[export_scale_name],
            "background": export_bg_name,
            "fontFamily": font_family,
            "fontSize": font_size,
        },
        "fontFamily": font_family,
        "fontSize": font_size,
        # resolution report (sections 5 and 7)
        "clamped": clamped,
        # colours only: a front-matter `themeVariables.fontSize` is reported
        # through sourceOf.textScale, not as a colour the user supplied
        "frontmatterColorKeys": sorted(
            k for k in fm_protected
            if is_hex_color(variables.get(k))),
        "sourceOf": source_of,
        "frozen": dict(FROZEN_SETTINGS),
        "family": family_name,
        "diagramType": diagram_type,
    }
    output.update(copy.deepcopy(FROZEN_SETTINGS))
    # Mermaid's own input ceilings (maxEdges 500 / maxTextSize 50 000 by
    # default) reject the largest documents this app must handle, and they are
    # *secure* settings: a diagram's own ``%%{init}`` block cannot set them. So
    # the resolver carries the raised values from the module constant - front
    # matter can never lower them, because no unknown key is read from it.
    output.update(copy.deepcopy(RENDER_LIMITS))
    return output


# ---------------------------------------------------------------------------
# Consumer helpers — one resolver, three consumers (A-2 / FR-008)
# ---------------------------------------------------------------------------

def build_mermaid_config_input(knobs, diagram_type, frontmatter=None):
    """The ResolvedAppearance object every consumer receives."""
    return resolve(knobs, diagram_type, frontmatter)


def build_mermaid_config_output(resolved):
    """The options object passed to mermaid.initialize (contract 2 rule 1).

    The whole ResolvedAppearance re-spelled for the library (``theme``) with
    the section 6 frozen settings and the module ``RENDER_LIMITS``.

    The limits are re-applied here, last, from the module constant, so nothing
    a diagram or a caller supplied can lower them: mermaid reads ``maxEdges``
    and ``maxTextSize`` only from this object (they are secure settings, never
    settable from diagram text), and without them a 1 265-edge document is
    reported as a parse failure instead of rendering (SC-003). ``resolve()``
    also carries the same values, so every consumer path - preview, export,
    link - initialises from one shape; this function remains the boundary that
    guarantees them.
    """
    out = copy.deepcopy(resolved)
    for key in ("clamped", "frontmatterColorKeys", "sourceOf", "family",
                "diagramType", "export", "diagram_config"):
        out.pop(key, None)
    out["theme"] = out.pop("mermaidTheme")
    for key, value in FROZEN_SETTINGS.items():
        out[key] = value
    for key in RENDER_LIMITS:
        out.pop(key, None)
    out.update(copy.deepcopy(RENDER_LIMITS))
    return out


def preview_config(resolved):
    """Consumer 1 (preview): receives the identical object."""
    return build_mermaid_config_output(resolved)


def export_config(resolved):
    """Consumer 2 (export): never re-resolves from UI state (FR-008)."""
    return copy.deepcopy(resolved)


def link_config(knobs, diagram_type, frontmatter=None):
    """Consumer 3 (link): recomputes from knobs identically to fresh input."""
    return resolve(knobs, diagram_type, frontmatter)


def assert_no_forbidden_keys(obj, path=""):
    """Section 3 guard: wordWrap / useMaxWidth / HTML-label options never set."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in FORBIDDEN_KEYS:
                raise AssertionError("forbidden key %r present at %s"
                                     % (key, path or "$"))
            assert_no_forbidden_keys(value, "%s.%s" % (path, key))
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            assert_no_forbidden_keys(item, "%s[%d]" % (path, index))


def to_json(resolved):
    """Deterministic serialisation for byte-equality assertions (A-2)."""
    return json.dumps(resolved, sort_keys=True, separators=(",", ":"))
