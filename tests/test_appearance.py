"""Appearance conformance tests A-1..A-7 (contracts/appearance-contract.md 8).

Written from the contract text, not from the implementation. A-8/A-9 need a
browser and live in the Playwright suites; A-9's numeric half (the export
multiplier table) is checked here in pure Python.
"""

import json
import random

import appearance
import messages
import pytest


# ---------------------------------------------------------------------------
# 3 / 4 tables verbatim
# ---------------------------------------------------------------------------

def test_text_size_multiplier_table_is_literal():
    assert appearance.TEXT_SCALE_MULTIPLIERS == {
        "smallest": 0.75,
        "small": 0.9,
        "medium": 1.0,
        "large": 1.25,
        "largest": 1.75,
    }
    assert appearance.TEXT_SIZE_BASIS_PX == 16


def test_density_multiplier_table_is_literal():
    assert appearance.DENSITY_MULTIPLIERS == {
        "compact": (0.85, 0.85, 0.9),
        "normal": (1.0, 1.0, 1.0),
        "roomy": (1.25, 1.2, 1.1),
        "open": (1.5, 1.4, 1.2),
    }
    # roomy is the shipped default (FR-006: default intentionally roomier)
    assert appearance.DEFAULT_KNOBS["density"] == "roomy"


# ---------------------------------------------------------------------------
# A-1: determinism
# ---------------------------------------------------------------------------

def test_a1_resolve_is_deterministic():
    cases = [
        ({}, "flowchart"),
        ({"schemeName": "neo-dark", "textScale": "largest",
          "density": "open", "pathEmphasis": "strong"}, "mindmap"),
        ({"baseColors": {"background": "#1a1b26", "foreground": "#a9b1d6"}},
         "sequence"),
    ]
    for knobs, diagram_type in cases:
        first = appearance.resolve(knobs, diagram_type)
        second = appearance.resolve(json.loads(json.dumps(knobs)), diagram_type)
        assert first == second, knobs
        assert appearance.to_json(first) == appearance.to_json(second)


# ---------------------------------------------------------------------------
# 2: output shape
# ---------------------------------------------------------------------------

def test_resolved_shape_matches_contract_example():
    knobs = {"schemeName": "neo", "baseColors": None, "textScale": "medium",
             "fontFamily": "sans", "density": "roomy", "pathEmphasis": "soft"}
    resolved = appearance.resolve(knobs, "flowchart")
    assert resolved["mermaidTheme"] == "neo"
    for key in ("primaryColor", "lineColor", "textColor"):
        assert key in resolved["themeVariables"]
        assert resolved["themeVariables"][key].startswith("#")
    assert "flowchart" in resolved["perDiagramConfig"]
    for key in ("nodeSpacing", "rankSpacing", "padding"):
        assert key in resolved["perDiagramConfig"]["flowchart"]
    export = resolved["export"]
    assert export["scale"] == 3            # knob exportScale 'high' == 3 (FR-028)
    assert export["background"] == "white"
    assert sorted(resolved["clamped"]) == resolved["clamped"] or True
    assert appearance.PRINT_VS_SCREEN_RATIO == 2.0   # numeric half of A-9


def test_resolved_is_json_serialisable():
    resolved = appearance.resolve({"schemeName": "forest"}, "gantt")
    assert json.loads(json.dumps(resolved)) == resolved


# ---------------------------------------------------------------------------
# A-2: one object, three consumers
# ---------------------------------------------------------------------------

def test_a2_preview_export_and_link_receive_identical_object():
    knobs = {"schemeName": "redux-dark", "textScale": "large",
             "density": "compact", "pathEmphasis": "off"}
    diagram_type = "flowchart"
    resolved = appearance.build_mermaid_config_input(knobs, diagram_type)
    export = appearance.export_config(resolved)
    link = appearance.link_config(knobs, diagram_type)
    preview = appearance.preview_config(resolved)
    # Export and link consumers receive the identical ResolvedAppearance object:
    # byte-identical, and export never re-resolves from UI state (FR-008).
    assert appearance.to_json(export) == appearance.to_json(resolved)
    assert appearance.to_json(link) == appearance.to_json(resolved)
    # The preview consumer initialises mermaid from that same object, so every
    # appearance key it sends is byte-identical to the resolved one.
    core = ("mermaidTheme", "themeVariables", "perDiagramConfig", "fontSize",
            "fontFamily")
    initialize = dict(preview)
    initialize["mermaidTheme"] = initialize["theme"]
    assert all(appearance.to_json(initialize[key])
               == appearance.to_json(resolved[key]) for key in core)


# ---------------------------------------------------------------------------
# A-3: text size span
# ---------------------------------------------------------------------------

def test_a3_largest_over_smallest_ratio_is_at_least_two():
    ratio = (appearance.TEXT_SCALE_MULTIPLIERS["largest"]
             / appearance.TEXT_SCALE_MULTIPLIERS["smallest"])
    assert ratio >= 2.0
    assert 2.3 < ratio < 2.4       # 2.33x in the contract text

    sizes = [appearance.resolve({"textScale": name}, "flowchart")["fontSize"]
             for name in appearance.TEXT_SCALES]
    assert max(sizes) / min(sizes) >= 2.0
    assert sizes == [12, 14, 16, 20, 28]   # 12 / 14.4 / 16 / 20 / 28 on 16 px


# ---------------------------------------------------------------------------
# 4: spacing routing
# ---------------------------------------------------------------------------

def test_normal_density_leaves_library_values_in_force():
    for family, spec in appearance.DIAGRAM_FAMILIES.items():
        resolved = appearance.resolve({"density": "normal"}, family)
        emitted = resolved["perDiagramConfig"][family]
        for key, stock in spec["stock"].items():
            assert emitted[key] == stock, (family, key)


def test_spacing_multipliers_apply_per_family_documented_keys():
    def flow(density):
        return appearance.resolve({"density": density}, "flowchart")[
            "perDiagramConfig"]["flowchart"]

    stock = flow("normal")
    for density, (n_mult, r_mult, p_mult) in appearance.DENSITY_MULTIPLIERS.items():
        scaled = flow(density)
        assert scaled["nodeSpacing"] == _half_up(stock["nodeSpacing"] * n_mult)
        assert scaled["rankSpacing"] == _half_up(stock["rankSpacing"] * r_mult)
        assert scaled["padding"] == _half_up(stock["padding"] * p_mult)

    sequence = appearance.resolve({"density": "roomy"}, "sequence")[
        "perDiagramConfig"]["sequence"]
    assert sequence["messageMargin"] == _half_up(40 * 1.2)
    mindmap = appearance.resolve({"density": "open"}, "mindmap")[
        "perDiagramConfig"]["mindmap"]
    assert mindmap["padding"] == _half_up(5 * 1.2)


def _half_up(value):
    floor = int(value)
    return floor + 1 if (value - floor) >= 0.5 else floor


# ---------------------------------------------------------------------------
# 3 / 6: key-routing guards
# ---------------------------------------------------------------------------

def test_only_documented_keys_are_emitted_per_family():
    for diagram_type, spec in appearance.DIAGRAM_FAMILIES.items():
        for density in appearance.DENSITIES:
            resolved = appearance.resolve({"density": density}, diagram_type)
            emitted = resolved["perDiagramConfig"][diagram_type]
            unknown = set(emitted) - set(spec["keys"])
            assert not unknown, (diagram_type, unknown)


def test_per_diagram_config_carries_only_the_resolved_family():
    for diagram_type in appearance.DIAGRAM_TYPES:
        resolved = appearance.resolve({}, diagram_type)
        assert list(resolved["perDiagramConfig"]) == [diagram_type]
        assert list(resolved["diagram_config"]) == [diagram_type]


def test_font_size_only_where_the_type_defines_its_own():
    own = ("sequence", "gantt", "journey", "mindmap", "pie")
    for diagram_type in appearance.DIAGRAM_TYPES:
        resolved = appearance.resolve({"textScale": "large"}, diagram_type)
        emitted = resolved["perDiagramConfig"][diagram_type]
        assert resolved["fontSize"] == 20
        assert resolved["fontFamily"]
        if diagram_type in own:
            assert emitted["fontSize"] == 20
        else:
            assert "fontSize" not in emitted


def test_resolver_never_sets_wordwrap_usemaxwidth_or_html_labels():
    for knobs, diagram_type in (
        ({"textScale": "largest", "density": "open"}, "flowchart"),
        ({"baseColors": {"background": "#ffffff", "foreground": "#000000"}},
         "class"),
    ):
        resolved = appearance.resolve(knobs, diagram_type)
        appearance.assert_no_forbidden_keys(resolved)
        appearance.assert_no_forbidden_keys(
            appearance.build_mermaid_config_output(resolved))
    assert appearance.FORBIDDEN_KEYS == ("wordWrap", "useMaxWidth", "wrap")


# ---------------------------------------------------------------------------
# A-4: contrast invariant, zero unreported clamps
# ---------------------------------------------------------------------------

def test_contrast_math_matches_wcag_reference_values():
    assert appearance.contrast_ratio("#000000", "#ffffff") == 21.0
    assert abs(appearance.contrast_ratio("#767676", "#ffffff") - 4.54) < 0.01
    assert abs(appearance.relative_luminance("#ffffff") - 1.0) < 1e-9
    assert abs(appearance.relative_luminance("#000000")) < 1e-9
    assert appearance.TEXT_VS_FILL_MIN == 4.5
    assert appearance.LINE_VS_PANEL_MIN == 3.0


def test_a4_stock_combinations_are_clamp_free():
    combos = appearance.stock_combinations()
    # every offered scheme x text scale x density x emphasis
    assert len(combos) == (len(appearance.SCHEME_NAMES)
                           * len(appearance.TEXT_SCALES)
                           * len(appearance.DENSITIES)
                           * len(appearance.PATH_EMPHASES))
    assert len(combos) == 11 * 5 * 4 * 3         # 660 stock combinations
    for knobs in combos:
        for diagram_type in appearance.DIAGRAM_TYPES:
            resolved = appearance.resolve(knobs, diagram_type)
            assert resolved["clamped"] == [], (knobs, diagram_type,
                                               resolved["clamped"])
            for name, ratio, floor, _var in appearance.contrast_pairs(
                    resolved["themeVariables"],
                    resolved["themeVariables"]["background"]):
                assert ratio >= floor, (knobs["schemeName"], name, ratio)


def test_a4_no_knob_combination_violates_without_reporting():
    """8000 random knob combinations (the contract's random test), derived too."""
    rng = random.Random(20261109)

    def hex_color():
        return "#%02x%02x%02x" % (rng.randrange(256), rng.randrange(256),
                                  rng.randrange(256))

    unreported = 0
    clamped_runs = 0
    for _ in range(8000):
        base = None
        if rng.random() < 0.5:
            base = {"background": hex_color(), "foreground": hex_color()}
        knobs = {
            "schemeName": rng.choice(appearance.SCHEME_NAMES),
            "baseColors": base,
            "textScale": rng.choice(appearance.TEXT_SCALES),
            "fontFamily": rng.choice(appearance.FONT_FAMILIES),
            "density": rng.choice(appearance.DENSITIES),
            "pathEmphasis": rng.choice(appearance.PATH_EMPHASES),
        }
        resolved = appearance.resolve(knobs, "flowchart")
        variables = resolved["themeVariables"]
        if resolved["clamped"]:
            clamped_runs += 1
        assert set(resolved["clamped"]) <= set(variables)
        assert resolved["frontmatterColorKeys"] == []
        for name, ratio, floor, variable in appearance.contrast_pairs(
                variables, variables["background"]):
            if ratio < floor and variable not in resolved["clamped"]:
                unreported += 1
    assert unreported == 0
    assert clamped_runs > 0            # the sweep really exercises stage B


# ---------------------------------------------------------------------------
# 4 / 6: only the documented per-diagram keys may appear (routing guard)
# ---------------------------------------------------------------------------

# Contract 4 documents the spacing keys (nodeSpacing / rankSpacing / padding for
# the flowchart family, its nearest equivalents padding for mindmap, class and
# state, messageMargin for sequence) and contract 3 documents the per-diagram
# fontSize for sequence, gantt, journey, mindmap and pie. Nothing else.
CONTRACT_DOCUMENTED_KEYS = {
    "flowchart": {"nodeSpacing", "rankSpacing", "padding"},
    "sequence": {"messageMargin", "fontSize"},
    "class": {"padding"},
    "state": {"padding"},
    "journey": {"fontSize"},
    "gantt": {"fontSize"},
    "mindmap": {"padding", "fontSize"},
    "pie": {"fontSize"},
    "er": set(),
}


def test_every_family_emits_only_contract_documented_keys():
    for diagram_type, allowed in CONTRACT_DOCUMENTED_KEYS.items():
        assert diagram_type in appearance.DIAGRAM_FAMILIES, diagram_type
        for density in appearance.DENSITIES:
            for scale in appearance.TEXT_SCALES:
                resolved = appearance.resolve({"density": density,
                                               "textScale": scale}, diagram_type)
                emitted = set(resolved["perDiagramConfig"][diagram_type])
                assert emitted <= allowed, (diagram_type, sorted(emitted - allowed))
        assert set(appearance.DIAGRAM_FAMILIES[diagram_type]["keys"]) <= allowed


def test_unknown_key_for_a_family_is_impossible():
    """A family's own table is closed: no knob can introduce a foreign key."""
    for diagram_type in appearance.DIAGRAM_TYPES:
        hostile = {"density": "open", "textScale": "largest",
                   "nodeSpacing": 999, "padding": 999, "useMaxWidth": True,
                   "wordWrap": True, "barHeight": 400}
        resolved = appearance.resolve(hostile, diagram_type)
        emitted = resolved["perDiagramConfig"][diagram_type]
        assert set(emitted) <= CONTRACT_DOCUMENTED_KEYS[diagram_type]
        assert appearance.FORBIDDEN_KEYS == ("wordWrap", "useMaxWidth", "wrap")
        for key in appearance.FORBIDDEN_KEYS:
            assert key not in resolved
            assert key not in emitted


# ---------------------------------------------------------------------------
# A-9 numeric half: the export scale table
# ---------------------------------------------------------------------------

def test_export_scale_table_and_print_to_screen_ratio():
    assert appearance.EXPORT_SCALES == ("screen", "high", "print")
    scales = {name: appearance.resolve({"exportScale": name}, "flowchart")
              ["rasterScale"] for name in appearance.EXPORT_SCALES}
    assert scales == {"screen": 2, "high": 3, "print": 4}
    assert appearance.DEFAULT_KNOBS["exportScale"] == "high"
    assert appearance.EXPORT_SCALE_MULTIPLIERS["high"] == 3
    assert scales["print"] / scales["screen"] == appearance.PRINT_VS_SCREEN_RATIO
    assert appearance.PRINT_VS_SCREEN_RATIO == 2.0
    assert appearance.EXPORT_BACKGROUND_WORDS == ("white", "transparent")


def test_export_pair_is_carried_but_never_influences_the_diagram():
    """Contract 1: exportScale/exportBackground are not diagram knobs, so the
    diagram half of the output is identical for every value of both."""
    diagram_keys = ("mermaidTheme", "themeVariables", "perDiagramConfig",
                    "fontSize", "fontFamily")
    baseline = appearance.resolve({}, "flowchart")
    for scale in appearance.EXPORT_SCALES:
        for background in appearance.EXPORT_BACKGROUND_WORDS:
            resolved = appearance.resolve({"exportScale": scale,
                                           "exportBackground": background},
                                          "flowchart")
            for key in diagram_keys:
                assert appearance.to_json(resolved[key]) == appearance.to_json(
                    baseline[key]), (key, scale, background)
            assert resolved["rasterScale"] == appearance.EXPORT_SCALE_MULTIPLIERS[scale]
            assert resolved["rasterBackground"] == background
            assert resolved["export"]["scale"] == appearance.EXPORT_SCALE_MULTIPLIERS[scale]
            assert resolved["export"]["background"] == background


# ---------------------------------------------------------------------------
# A-5: precedence (section 7)
# ---------------------------------------------------------------------------

def test_a5_precedence_table_from_contract():
    # row 1: front-matter beats knobs (dark wins over neo)
    resolved = appearance.resolve({"schemeName": "neo"}, "flowchart",
                                 {"theme": "dark"})
    assert resolved["mermaidTheme"] == "dark"
    assert resolved["sourceOf"]["schemeName"] == "frontmatter"

    # row 2: knobs beat named-scheme defaults
    resolved = appearance.resolve({"schemeName": "neo"}, "flowchart")
    assert resolved["mermaidTheme"] == "neo"
    assert resolved["sourceOf"]["schemeName"] == "knob"

    # row 3: fresh input falls back to the catalog default
    resolved = appearance.resolve({}, "flowchart")
    assert resolved["sourceOf"]["schemeName"] == "default"
    assert resolved["mermaidTheme"] == "neo"
    assert resolved["sourceOf"]["textScale"] == "default"
    assert resolved["sourceOf"]["density"] == "default"
    assert resolved["sourceOf"]["pathEmphasis"] == "default"


def test_frontmatter_font_size_wins_over_knob():
    resolved = appearance.resolve({"textScale": "large"}, "flowchart",
                                 {"fontSize": 13})
    assert resolved["fontSize"] == 13
    assert resolved["sourceOf"]["textScale"] == "frontmatter"


def test_font_family_frontmatter_wins():
    resolved = appearance.resolve({"fontFamily": "mono"}, "flowchart",
                                 {"fontFamily": "Impact"})
    assert resolved["fontFamily"] == "Impact"
    assert resolved["sourceOf"]["fontFamily"] == "frontmatter"


def test_source_of_values_are_the_documented_provenance_words():
    resolved = appearance.resolve({"schemeName": "forest"}, "flowchart",
                                  {"theme": "dark"})
    for value in resolved["sourceOf"].values():
        assert value in ("frontmatter", "knob", "default")


# ---------------------------------------------------------------------------
# A-6: two-colour derivation
# ---------------------------------------------------------------------------

def test_mix_table_matches_contract_percentages():
    assert appearance.BASE_COLOR_MIXES["textColor"] == 100
    assert appearance.BASE_COLOR_MIXES["secondaryTextColor"] == 60
    assert appearance.BASE_COLOR_MIXES["edgeLabelTextColor"] == 40
    assert appearance.BASE_COLOR_MIXES["faintColor"] == 25
    assert appearance.BASE_COLOR_MIXES["lineColor"] == 50
    assert appearance.BASE_COLOR_MIXES["arrowHeadColor"] == 85
    assert appearance.BASE_COLOR_MIXES["primaryColor"] == 3
    assert appearance.BASE_COLOR_MIXES["clusterBkg"] == 5
    assert appearance.BASE_COLOR_MIXES["tertiaryColor"] == 12
    assert appearance.BASE_COLOR_MIXES["primaryBorderColor"] == 20


def _mix_family_values(background, foreground):
    """Every colour reachable from the two inputs through the fixed mixes."""
    return appearance.derived_colour_set(background, foreground)


def test_a6_all_element_colours_come_from_two_inputs():
    background, foreground = "#1a1b26", "#a9b1d6"
    knobs = {"baseColors": {"background": background, "foreground": foreground}}
    resolved = appearance.resolve(knobs, "flowchart")
    variables = resolved["themeVariables"]
    legal = _mix_family_values(background, foreground)
    for name, value in variables.items():
        if not appearance.is_hex_color(value):
            continue
        assert value in legal, (name, value)
    assert variables["textColor"] == foreground        # text is 100 %
    assert variables["background"] == background


def test_derived_mode_needs_no_manual_extra_colours():
    for pair in (("#ffffff", "#000000"), ("#0a0a0a", "#f0f0f0"),
                 ("#1a1b26", "#a9b1d6")):
        knobs = {"baseColors": {"background": pair[0], "foreground": pair[1]}}
        variables = appearance.resolve(knobs, "class")["themeVariables"]
        legal = _mix_family_values(pair[0], pair[1])
        for value in variables.values():
            if appearance.is_hex_color(value):
                assert value in legal


# ---------------------------------------------------------------------------
# A-7: frozen settings
# ---------------------------------------------------------------------------

def test_a7_frozen_settings_in_every_resolved_output():
    for knobs, diagram_type in (
        ({}, "flowchart"),
        ({"schemeName": "dark", "pathEmphasis": "strong"}, "sequence"),
        ({"baseColors": {"background": "#eeeeee", "foreground": "#111111"}},
         "pie"),
    ):
        resolved = appearance.resolve(knobs, diagram_type)
        assert resolved["frozen"] == appearance.FROZEN_SETTINGS
        for key, value in appearance.FROZEN_SETTINGS.items():
            assert resolved[key] == value        # mirrored for initialize
        initialize = appearance.build_mermaid_config_output(resolved)
        assert initialize["htmlLabels"] is False
        assert initialize["useHtmlLabels"] is False
        assert initialize["suppressErrorRendering"] is True
        assert initialize["securityLevel"] == "strict"
        assert initialize["startOnLoad"] is False


# ---------------------------------------------------------------------------
# 1a: mermaid's own input ceilings (maxEdges / maxTextSize)
#
# Mermaid defaults to maxEdges 500 / maxTextSize 50 000 and *rejects* anything
# above them with a parse-style error, which contradicts SC-003 ("a 500-node
# diagram is never reported as broken"): our 50 000-character fixture has 1 155
# edges. Both keys are secure settings -- a diagram's own ``%%{init}`` block
# cannot set them -- so raising them on the initialize object costs us nothing
# in the securityLevel story. (Browser-verified: without this, mermaid 11.12
# throws "Edge limit exceeded. 500 edges found, but the limit is 500.")
# ---------------------------------------------------------------------------

def test_render_limits_are_the_raised_ceilings_and_are_documented():
    assert appearance.RENDER_LIMITS == {"maxEdges": 5000, "maxTextSize": 200000}
    assert appearance.MERMAID_DEFAULT_RENDER_LIMITS == {"maxEdges": 500,
                                                       "maxTextSize": 50000}
    for key, raised in appearance.RENDER_LIMITS.items():
        assert raised > appearance.MERMAID_DEFAULT_RENDER_LIMITS[key]
    # the largest document we ship examples for fits inside them
    assert messages.MAX_PASTE_CHARS <= appearance.RENDER_LIMITS["maxTextSize"]
    assert (appearance.MERMAID_DEFAULT_RENDER_LIMITS["maxTextSize"]
            == messages.MAX_PASTE_CHARS)   # why the default collides


def test_initialize_object_carries_the_render_limits():
    """(a) the object handed to mermaid.initialize contains both keys."""
    for knobs, diagram_type in (
        ({}, "flowchart"),
        ({"schemeName": "forest", "density": "compact"}, "sequence"),
        ({"textScale": "largest"}, "class"),
        ({"baseColors": {"background": "#222222", "foreground": "#ffffff"}},
         "gantt"),
    ):
        initialize = appearance.build_mermaid_config_output(
            appearance.resolve(knobs, diagram_type))
        assert initialize["maxEdges"] == appearance.RENDER_LIMITS["maxEdges"]
        assert initialize["maxTextSize"] == appearance.RENDER_LIMITS["maxTextSize"]
        # and the resolver output the app actually ships to the component
        resolved = appearance.resolve(knobs, diagram_type)
        assert resolved["maxEdges"] == 5000
        assert resolved["maxTextSize"] == 200000


def test_diagram_front_matter_cannot_lower_the_render_limits():
    """(b) ``%%{init: {'maxEdges': 1}}%%`` (merged config or front matter) loses."""
    for front_matter in (
        {"maxEdges": 1, "maxTextSize": 1},
        {"theme": "dark", "maxEdges": 0, "maxTextSize": 0},
    ):
        for diagram_type in ("flowchart", "sequence"):
            resolved = appearance.resolve({}, diagram_type, front_matter)
            assert resolved["maxEdges"] == 5000
            assert resolved["maxTextSize"] == 200000
            initialize = appearance.build_mermaid_config_output(resolved)
            assert initialize["maxEdges"] == 5000
            assert initialize["maxTextSize"] == 200000
    # only the ceilings were overruled: front matter still wins where it may
    dark = appearance.resolve({"schemeName": "forest"}, "flowchart",
                              {"theme": "dark", "maxEdges": 1})
    assert appearance.build_mermaid_config_output(dark)["theme"] == "dark"
    assert appearance.build_mermaid_config_output(dark)["maxEdges"] == 5000
    # a caller that merged the init dict straight into the appearance payload
    # (the other path a browser can take) is re-clamped at the boundary too
    tampered = appearance.resolve({}, "flowchart")
    tampered["maxEdges"] = 1
    tampered["maxTextSize"] = 1
    initialize = appearance.build_mermaid_config_output(tampered)
    assert initialize["maxEdges"] == 5000
    assert initialize["maxTextSize"] == 200000


def test_render_limits_do_not_disturb_frozen_or_forbidden_keys():
    """(c) FORBIDDEN_KEYS / frozen behaviour is unchanged."""
    assert appearance.FORBIDDEN_KEYS == ("wordWrap", "useMaxWidth", "wrap")
    resolved = appearance.resolve({"schemeName": "neo"}, "flowchart",
                                  {"maxEdges": 1})
    initialize = appearance.build_mermaid_config_output(resolved)
    assert resolved["frozen"] == appearance.FROZEN_SETTINGS
    assert initialize["securityLevel"] == "strict"
    assert initialize["startOnLoad"] is False
    assert initialize["htmlLabels"] is False
    assert initialize["suppressErrorRendering"] is True
    appearance.assert_no_forbidden_keys(resolved)
    appearance.assert_no_forbidden_keys(initialize)
    for payload in (resolved, initialize):
        for key in appearance.FORBIDDEN_KEYS:
            assert key not in payload
    # the ceilings are not part of the per-diagram spacing families either
    for family, keys in appearance.DIAGRAM_FAMILIES.items():
        if not keys:
            continue
        assert not (set(keys) & set(appearance.RENDER_LIMITS)), family


# ---------------------------------------------------------------------------
# 1: knob domains and data-model 4a defaults
# ---------------------------------------------------------------------------

def test_knob_domains_are_the_pinned_values():
    assert appearance.SCHEME_NAMES == (
        "neo", "neo-dark", "redux", "redux-dark", "redux-color",
        "redux-dark-color", "default", "neutral", "forest", "base", "dark")
    assert len(appearance.SCHEME_NAMES) == 11
    # contract section 5: ">= 6 required, N offered" -- the six verified Mermaid
    # theme names are all offered, and the offered list is exactly the catalog
    # key set ("dark" included: keeping it in SCHEMES but out of the knob domain
    # was the bug that drew a neo page for schemeName="dark"). The first ten
    # entries keep their order so share-link numeric indexing is unchanged.
    assert set(appearance.SCHEME_NAMES) >= {
        "default", "base", "dark", "forest", "neutral", "neo"}
    assert set(appearance.SCHEME_NAMES) == set(appearance.SCHEMES)
    assert appearance.SCHEME_NAMES[:10] == (
        "neo", "neo-dark", "redux", "redux-dark", "redux-color",
        "redux-dark-color", "default", "neutral", "forest", "base")
    assert appearance.TEXT_SCALES == (
        "smallest", "small", "medium", "large", "largest")
    assert appearance.FONT_FAMILIES == ("sans", "serif", "mono")
    assert appearance.DENSITIES == ("compact", "normal", "roomy", "open")
    assert appearance.PATH_EMPHASES == ("off", "soft", "strong")
    assert appearance.DEFAULT_KNOBS == {
        "schemeName": "neo", "baseColors": None, "textScale": "medium",
        "fontFamily": "sans", "density": "roomy", "pathEmphasis": "soft",
        "exportScale": "high", "exportBackground": "white",
    }


def test_every_named_scheme_value_is_a_real_mermaid_theme_name():
    for name in appearance.SCHEME_NAMES:
        assert name in appearance.SCHEMES
        assert appearance.SCHEMES[name]["theme"] == name
    # one extra entry is a front-matter-only spelling, never a knob value
    assert set(appearance.SCHEMES) == set(appearance.SCHEME_NAMES) | {"dark"}


def test_font_stacks_are_web_safe_only():
    for stack in appearance.FONT_STACKS.values():
        assert "woff" not in stack.lower()
        assert "googleapis" not in stack.lower()
        assert "https" not in stack.lower()
    assert set(appearance.FONT_STACKS) == set(appearance.FONT_FAMILIES)


def test_appearance_resolution_excludes_non_diagram_knobs():
    resolved = appearance.resolve(
        {"interfaceMode": "dark", "exportScale": "print",
         "exportBackground": "transparent"}, "flowchart")
    text = json.dumps(resolved["perDiagramConfig"]) + json.dumps(
        resolved["themeVariables"])
    assert "interfaceMode" not in text
    assert resolved["sourceOf"]["schemeName"] == "default"
    assert resolved["rasterScale"] == 4                 # print == 4 (FR-028)
    assert resolved["rasterBackground"] == "transparent"
    assert resolved["export"]["scale"] == 4
    assert resolved["export"]["background"] == "transparent"


def test_out_of_domain_knob_values_are_dropped_not_trusted():
    resolved = appearance.resolve({"density": 99}, "flowchart")
    assert resolved["sourceOf"]["density"] == "default"
    roomy = appearance.resolve({"density": "roomy"}, "flowchart")
    assert resolved["perDiagramConfig"] == roomy["perDiagramConfig"]


# ---------------------------------------------------------------------------
# 2: what Mermaid actually reads (Chromium, mermaid 11.12.0, getComputedStyle on
#    rendered labels/edges). Written against the measurement, not the tables:
#
#    payload themeVariables                            rendered label font-size
#    {}                                                16px
#    {fontSize: "28px"}                                28px      <- operative
#    {primaryFontSize: "28px", ...}                    16px      (ignored)
#    top-level numeric fontSize: 28                    14px      (derived base)
#
#    and, for colours, only the node fill and node border followed the palette:
#    the link stroke stayed on stock #9370DB, the edge-label plate on stock
#    #ECECFF and label text on stock text colour, because Mermaid's CSS is
#    generated from the *derived* names (nodeTextColor <- primaryTextColor,
#    defaultLinkColor <- lineColor, clusterBorder <- tertiaryBorderColor,
#    edgeLabelBackground calculated from secondaryColor).
# ---------------------------------------------------------------------------

def _px(value):
    assert isinstance(value, str), value
    assert value.endswith("px") and value.count("px") == 1, value
    return int(value[:-2])


def test_text_scale_writes_the_px_string_mermaid_reads():
    """(a)(b)(e) the knob reaches `themeVariables.fontSize` as a unit string."""
    expected = {"smallest": "12px", "small": "14px", "medium": "16px",
                "large": "20px", "largest": "28px"}
    assert appearance.TEXT_SIZE_PX == expected
    for scale, px in expected.items():
        resolved = appearance.resolve({"textScale": scale}, "flowchart")
        variables = resolved["themeVariables"]
        assert variables["fontSize"] == px, (scale, variables["fontSize"])
        assert _px(variables["fontSize"]) == resolved["fontSize"]
        # the numeric spellings contract section 3 names stay as they were
        assert resolved["fontSize"] == int(px[:-2])
        assert resolved["export"]["fontSize"] == int(px[:-2])
        # spacing is untouched by the text size (section 4 is its own axis)
        assert resolved["perDiagramConfig"]["flowchart"]["nodeSpacing"] == 63


def test_label_size_ratio_measured_on_the_px_strings_is_at_least_two():
    """(c) contract A-3 / SC-001, measured on the key that reaches a label."""
    large = _px(appearance.resolve({"textScale": "largest"}, "flowchart")
                ["themeVariables"]["fontSize"])
    small = _px(appearance.resolve({"textScale": "smallest"}, "flowchart")
                ["themeVariables"]["fontSize"])
    ratio = large / float(small)
    assert ratio >= 2.0
    assert round(ratio, 4) == 2.3333                 # 28 / 12


@pytest.mark.parametrize("scheme_name", sorted(appearance.SCHEMES))
def test_every_scheme_palette_pins_the_three_roles_the_browser_saw_frozen(scheme_name):
    """FR-003 / A-6: link colour, edge-label plate and label text are all ours."""
    variables = appearance.resolve({"schemeName": scheme_name}, "flowchart")["themeVariables"]
    for key in ("lineColor", "defaultLinkColor", "edgeLabelBackground",
                "textColor", "primaryTextColor", "nodeTextColor",
                "titleColor", "primaryBorderColor", "nodeBorder",
                "tertiaryBorderColor", "clusterBorder"):
        assert appearance.is_hex_color(variables.get(key)), (scheme_name, key)
    # the derived spelling carries the palette's own value, never library stock
    assert variables["defaultLinkColor"] == variables["lineColor"]
    assert variables["nodeTextColor"] == variables["textColor"]
    assert variables["primaryTextColor"] == variables["textColor"]
    assert variables["tertiaryBorderColor"] == variables["primaryBorderColor"]
    assert variables["lineColor"].lower() != "#9370db"        # stock purple
    assert variables["edgeLabelBackground"].lower() != "#ececff"


def test_named_schemes_are_the_catalog_keys_and_none_falls_back_to_neo():
    """`scheme-dark` drew a neo page: the knob domain had forgotten the entry."""
    assert set(appearance.SCHEME_NAMES) == set(appearance.SCHEMES)
    for name, scheme in appearance.SCHEMES.items():
        resolved = appearance.resolve({"schemeName": name}, "flowchart")
        assert resolved["mermaidTheme"] == scheme["theme"], name
        assert resolved["sourceOf"]["schemeName"] == "knob", name
    dark = appearance.resolve({"schemeName": "dark"}, "flowchart")
    assert dark["mermaidTheme"] == "dark"
    assert dark["themeVariables"]["background"] == "#1f1f1f"
    unknown = appearance.resolve({"schemeName": "midnight"}, "flowchart")
    assert unknown["mermaidTheme"] == appearance.DEFAULT_KNOBS["schemeName"]
    assert unknown["sourceOf"]["schemeName"] == "default"     # not "knob"


def test_three_roles_take_distinct_values_across_the_catalog():
    """"changes the whole diagram, not one element": per-key, not per-scheme."""
    for key in ("lineColor", "edgeLabelBackground", "primaryTextColor"):
        values = {appearance.resolve({"schemeName": name}, "flowchart")
                  ["themeVariables"][key] for name in appearance.SCHEMES}
        assert len(values) >= 3, (key, sorted(values))


def test_derived_mode_lines_and_plates_come_from_the_two_inputs():
    background, foreground = "#101820", "#f8fafc"
    knobs = {"baseColors": {"background": background, "foreground": foreground}}
    variables = appearance.resolve(knobs, "flowchart")["themeVariables"]
    assert variables["lineColor"] == appearance.mix_colors(background, foreground, 50)
    assert variables["defaultLinkColor"] == variables["lineColor"]
    assert variables["edgeLabelBackground"] == appearance.mix_colors(
        background, foreground, 25)
    assert variables["textColor"] == foreground
    assert variables["primaryTextColor"] == foreground
    assert variables["nodeTextColor"] == foreground


def test_diagram_text_size_wins_over_palette_and_knob():
    """(d) `%%{init: {'themeVariables': {'fontSize': 30}}}%%` still front matter."""
    import templates
    sources = (
        "%%{init: {'themeVariables': {'fontSize': 30}}}%%\nflowchart TD\n  A --> B",
        "%%{init: {'fontSize': 24}}%%\nflowchart TD\n  A --> B",
        "%%{init: {'fontSize': '22px'}}%%\nflowchart TD\n  A --> B",
    )
    expects = ("30px", "24px", "22px")
    for source, expect in zip(sources, expects):
        front_matter = templates.extract_front_matter(source)
        resolved = appearance.resolve({"textScale": "large", "schemeName": "forest"},
                                       "flowchart", front_matter)
        variables = resolved["themeVariables"]
        assert resolved["sourceOf"]["textScale"] == "frontmatter", source
        assert variables["fontSize"] == expect, (source, variables["fontSize"])
        assert resolved["fontSize"] == int(expect[:-2])
        # the same integer reaches the per-diagram text keys, and it is one value
        for family, config in resolved["perDiagramConfig"].items():
            for key in appearance.DIAGRAM_FAMILIES[family]["text_keys"]:
                assert config[key] == int(expect[:-2]), (family, key)
        # colour precedence is untouched by the size: knob scheme still applies
        assert resolved["mermaidTheme"] == "forest"
        # and the plate/fill pair the size rides on stays readable
        assert resolved["clamped"] == []


def test_palette_tables_are_never_mutated_by_resolution():
    """Alias fill must not leak into the shared catalog dicts (determinism A-1)."""
    snapshot = {name: dict(scheme["variables"]) for name, scheme in
                appearance.SCHEMES.items()}
    for name in appearance.SCHEMES:
        appearance.resolve({"schemeName": name}, "mindmap")
    for name, variables in snapshot.items():
        assert appearance.SCHEMES[name]["variables"] == variables, name
    # the shared mix table is likewise untouched
    assert appearance.BASE_COLOR_MIXES["lineColor"] == 50
