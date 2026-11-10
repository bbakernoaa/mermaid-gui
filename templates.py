"""templates.py — diagram-type catalog (contracts/template-catalog-contract.md).

Data only, standard library only. Nine required ``typeId``s plus the ``blank``
pseudo-entry, each type carrying exactly one ``plain`` example and at least one
``styled`` example (FR-017/FR-018). ``typeId`` values match what
``mermaid.parse()`` reports as ``ParseResult.diagramType`` (research R-8) —
mermaid@11 feature names, lower-case (``flowchart-v2`` reports ``flowchart``).

``first_example(type_id)`` and ``label_for(type_id)`` are the app-integration
helpers consumed by ``app.py`` (FR-020/FR-021 wording lives here, not scattered).
"""

MAX_LABEL_CHARS = 96

REQUIRED_TYPE_IDS = ("flowchart", "sequence", "class", "state", "er", "gantt",
                     "pie", "journey", "mindmap")
BLANK_TYPE_ID = "blank"

# First keyword of every example body, per documented grammar. Used by the
# pure-Python conformance check; the authoritative detection in the app remains
# ParseResult.diagramType (research R-8).
TYPE_KEYWORDS = {
    "flowchart": ("flowchart", "graph"),
    "sequence": ("sequenceDiagram",),
    "class": ("classDiagram", "classDiagram-v2"),
    "state": ("stateDiagram", "stateDiagram-v2"),
    "er": ("erDiagram",),
    "gantt": ("gantt",),
    "pie": ("pie",),
    "journey": ("journey",),
    "mindmap": ("mindmap",),
}

# ---------------------------------------------------------------------------
# Examples: plain (no authoring aids) and styled (configuration carried in the
# front-matter, which is where mermaid itself reads it from).
# ---------------------------------------------------------------------------

CATALOG = {
    "flowchart": {
        "typeId": "flowchart",
        "label": "Flowchart",
        "blurb": "Steps, decisions and process flow",
        "examples": [
            {
                "exampleId": "flowchart-plain",
                "purpose": "plain",
                "minElements": 3,
                "source": (
                    "flowchart TD\n"
                    "    A[Read the source] --> B[Parse it]\n"
                    "    B --> C{Valid?}\n"
                    "    C -->|yes| D[Render preview]\n"
                    "    C -->|no| E[Show the line number]\n"
                ),
            },
            {
                "exampleId": "flowchart-styled",
                "purpose": "styled",
                "shows": "front-matter theme and node styling",
                "minElements": 3,
                "source": (
                    "---\n"
                    "config:\n"
                    "  theme: neo\n"
                    "---\n"
                    "flowchart LR\n"
                    "    A(Start) --> B[Collect input]\n"
                    "    B --> C[Validate]\n"
                    "    C --> D{OK}\n"
                    "    D -->|pass| E[Ship it]\n"
                    "    style E fill:#d5f6e2,stroke:#2d8659\n"
                ),
            },
        ],
    },
    "sequence": {
        "typeId": "sequence",
        "label": "Sequence diagram",
        "blurb": "Messages exchanged over time between actors",
        "examples": [
            {
                "exampleId": "sequence-plain",
                "purpose": "plain",
                "minElements": 3,
                "source": (
                    "sequenceDiagram\n"
                    "    participant User\n"
                    "    participant Editor\n"
                    "    participant Renderer\n"
                    "    User->>Editor: Type diagram text\n"
                    "    Editor->>Renderer: Parse and render\n"
                    "    Renderer-->>User: Show preview\n"
                ),
            },
            {
                "exampleId": "sequence-styled",
                "purpose": "styled",
                "shows": "autonumber, actor lanes, notes and activations",
                "minElements": 3,
                "source": (
                    "---\n"
                    "config:\n"
                    "  theme: neo\n"
                    "---\n"
                    "sequenceDiagram\n"
                    "    autonumber\n"
                    "    actor Customer\n"
                    "    participant App as Mermaid editor\n"
                    "    participant Svc as Render service\n"
                    "    Customer->>App: Paste diagram text\n"
                    "    activate App\n"
                    "    App->>Svc: Parse request\n"
                    "    Svc-->>App: Status rendered\n"
                    "    deactivate App\n"
                    "    Note over App,Svc: preview updates without a reload\n"
                ),
            },
        ],
    },
    "class": {
        "typeId": "class",
        "label": "Class diagram",
        "blurb": "Types, interfaces and their relationships",
        "examples": [
            {
                "exampleId": "class-plain",
                "purpose": "plain",
                "minElements": 3,
                "source": (
                    "classDiagram\n"
                    "    class Shape {\n"
                    "        +String name\n"
                    "        +area() float\n"
                    "    }\n"
                    "    class Circle {\n"
                    "        +float radius\n"
                    "        +area() float\n"
                    "    }\n"
                    "    class Drawable {\n"
                    "        <<interface>>\n"
                    "        +draw()\n"
                    "    }\n"
                    "    Shape <|-- Circle\n"
                    "    Drawable <|.. Circle\n"
                ),
            },
            {
                "exampleId": "class-styled",
                "purpose": "styled",
                "shows": "stereotypes, namespaces and relationship notes",
                "minElements": 3,
                "source": (
                    "---\n"
                    "config:\n"
                    "  theme: neo\n"
                    "---\n"
                    "classDiagram\n"
                    "    namespace Model {\n"
                    "        class Document {\n"
                    "            +String name\n"
                    "            +String source\n"
                    "        }\n"
                    "        class Appearance {\n"
                    "            +String schemeName\n"
                    "            +String density\n"
                    "        }\n"
                    "    }\n"
                    "    class Logger {\n"
                    "        <<singleton>>\n"
                    "        +log(msg)\n"
                    "    }\n"
                    "    Document --> Appearance : resolved by\n"
                    "    Document ..> Logger : annotates\n"
                    "    note for Document \"keeps the raw user text\"\n"
                ),
            },
        ],
    },
    "state": {
        "typeId": "state",
        "label": "State diagram",
        "blurb": "Lifecycle: states, transitions and their triggers",
        "examples": [
            {
                "exampleId": "state-plain",
                "purpose": "plain",
                "minElements": 3,
                "source": (
                    "stateDiagram-v2\n"
                    "    [*] --> empty\n"
                    "    empty --> rendering : source changes\n"
                    "    rendering --> rendered : parse and draw OK\n"
                    "    rendering --> invalid : parse fails\n"
                    "    invalid --> rendering : source changes\n"
                    "    rendered --> rendering : source changes\n"
                    "    rendered --> [*]\n"
                ),
            },
            {
                "exampleId": "state-styled",
                "purpose": "styled",
                "shows": "composite states and choice points",
                "minElements": 3,
                "source": (
                    "---\n"
                    "config:\n"
                    "  theme: neo\n"
                    "---\n"
                    "stateDiagram-v2\n"
                    "    [*] --> Draft\n"
                    "    state Draft {\n"
                    "        [*] --> Editing\n"
                    "        Editing --> Saved : autosave\n"
                    "        Saved --> Editing : keep typing\n"
                    "    }\n"
                    "    Draft --> Shared : create link\n"
                    "    Shared --> Draft : link decoded\n"
                    "    state check <<choice>>\n"
                    "    Draft --> check\n"
                    "    check --> Discarded : start fresh\n"
                    "    Discarded --> [*]\n"
                ),
            },
        ],
    },
    "er": {
        "typeId": "er",
        "label": "Entity-relationship diagram",
        "blurb": "Data entities, attributes and cardinality",
        "examples": [
            {
                "exampleId": "er-plain",
                "purpose": "plain",
                "minElements": 3,
                "source": (
                    "erDiagram\n"
                    "    DOCUMENT ||--o{ REVISION : has\n"
                    "    DOCUMENT {\n"
                    "        string name\n"
                    "        string source\n"
                    "    }\n"
                    "    REVISION {\n"
                    "        int number\n"
                    "        string savedAt\n"
                    "    }\n"
                    "    USER ||--o{ DOCUMENT : owns\n"
                ),
            },
            {
                "exampleId": "er-styled",
                "purpose": "styled",
                "shows": "identifiers, attribute comments and many-to-many links",
                "minElements": 3,
                "source": (
                    "---\n"
                    "config:\n"
                    "  theme: neo\n"
                    "---\n"
                    "erDiagram\n"
                    "    USER ||--o{ DOCUMENT : authors\n"
                    "    DOCUMENT }o--o{ TAG : carries\n"
                    "    DOCUMENT {\n"
                    "        string name \"filename stem\"\n"
                    "        string diagramType \"detected by the parser\"\n"
                    "    }\n"
                    "    TAG {\n"
                    "        string label\n"
                    "    }\n"
                    "    USER {\n"
                    "        string id PK\n"
                    "        string handle\n"
                    "    }\n"
                ),
            },
        ],
    },
    "gantt": {
        "typeId": "gantt",
        "label": "Gantt chart",
        "blurb": "Scheduled work over calendar time",
        "examples": [
            {
                "exampleId": "gantt-plain",
                "purpose": "plain",
                "minElements": 3,
                "source": (
                    "gantt\n"
                    "    title Release plan\n"
                    "    dateFormat YYYY-MM-DD\n"
                    "    section Build\n"
                    "    Layout        :a1, 2026-11-09, 3d\n"
                    "    Appearance    :a2, after a1, 5d\n"
                    "    section Ship\n"
                    "    Deploy        :b1, after a2, 2d\n"
                ),
            },
            {
                "exampleId": "gantt-styled",
                "purpose": "styled",
                "shows": "milestones, critical and completed tasks",
                "minElements": 3,
                "source": (
                    "---\n"
                    "config:\n"
                    "  theme: neo\n"
                    "---\n"
                    "gantt\n"
                    "    title Editor upgrade rollout\n"
                    "    dateFormat YYYY-MM-DD\n"
                    "    axisFormat %d %b\n"
                    "    todayMarker off\n"
                    "    section Design\n"
                    "    Contracts signed   :done, des1, 2026-10-20, 14d\n"
                    "    Palette review     :active, des2, after des1, 5d\n"
                    "    section Deliver\n"
                    "    Bridge wiring      :crit, dev1, after des2, 7d\n"
                    "    Smoke tests        :dev2, after dev1, 3d\n"
                    "    Release gate       :milestone, m1, after dev2, 0d\n"
                ),
            },
        ],
    },
    "pie": {
        "typeId": "pie",
        "label": "Pie chart",
        "blurb": "Part-to-whole proportions at a glance",
        "examples": [
            {
                "exampleId": "pie-plain",
                "purpose": "plain",
                "minElements": 3,
                "source": (
                    "pie showData\n"
                    "    title Where the time goes\n"
                    "    \"Editing\" : 45\n"
                    "    \"Reviewing\" : 30\n"
                    "    \"Exporting\" : 25\n"
                ),
            },
            {
                "exampleId": "pie-styled",
                "purpose": "styled",
                "shows": "four slices with a front-matter theme",
                "minElements": 3,
                "source": (
                    "---\n"
                    "config:\n"
                    "  theme: neo\n"
                    "---\n"
                    "pie showData\n"
                    "    title Diagram types requested\n"
                    "    \"Flowcharts\" : 220\n"
                    "    \"Sequences\" : 96\n"
                    "    \"Class diagrams\" : 58\n"
                    "    \"Everything else\" : 31\n"
                ),
            },
        ],
    },
    "journey": {
        "typeId": "journey",
        "label": "User journey",
        "blurb": "Experiences per step, scored by satisfaction",
        "examples": [
            {
                "exampleId": "journey-plain",
                "purpose": "plain",
                "minElements": 3,
                "source": (
                    "journey\n"
                    "    title Sharing a diagram\n"
                    "    section Draft\n"
                    "      Type text: 3: Author\n"
                    "      See preview: 4: Author\n"
                    "    section Share\n"
                    "      Copy link: 5: Author\n"
                    "      Open link: 2: Reviewer\n"
                ),
            },
            {
                "exampleId": "journey-styled",
                "purpose": "styled",
                "shows": "multi-role steps across three sections",
                "minElements": 3,
                "source": (
                    "---\n"
                    "config:\n"
                    "  theme: neo\n"
                    "---\n"
                    "journey\n"
                    "    title Editor first hour\n"
                    "    section Discover\n"
                    "      Find the app: 4: Visitor\n"
                    "      Pick a type: 5: Visitor\n"
                    "    section Compose\n"
                    "      Adjust appearance: 3: Author\n"
                    "      Hit a syntax error: 1: Author\n"
                    "    section Recover\n"
                    "      Read the line number: 4: Author, QA\n"
                    "      Fix it, preview returns: 5: Author\n"
                ),
            },
        ],
    },
    "mindmap": {
        "typeId": "mindmap",
        "label": "Mindmap",
        "blurb": "Free-form hierarchical brainstorming",
        "examples": [
            {
                "exampleId": "mindmap-plain",
                "purpose": "plain",
                "minElements": 3,
                "source": (
                    "mindmap\n"
                    "  ((Diagram editor))\n"
                    "    Appearance\n"
                    "      Text size\n"
                    "      Spacing\n"
                    "    Feedback\n"
                    "      Four states\n"
                    "      Line numbers\n"
                    "    Sharing\n"
                    "      Drafts\n"
                    "      Links\n"
                ),
            },
            {
                "exampleId": "mindmap-styled",
                "purpose": "styled",
                "shows": "shape syntax for nodes at depth",
                "minElements": 3,
                "source": (
                    "---\n"
                    "config:\n"
                    "  theme: neo\n"
                    "---\n"
                    "mindmap\n"
                    "  ((Experience upgrade))\n"
                    "    [Look and feel]\n"
                    "      (Scheme picker)\n"
                    "      (Two-colour derivation)\n"
                    "    [Trust]\n"
                    "      (Honest errors)\n"
                    "      (Last good render)\n"
                    "    [Reach]\n"
                    "      (Shared links)\n"
                    "      (Local drafts)\n"
                ),
            },
        ],
    },
    "blank": {
        "typeId": "blank",
        "label": "Blank diagram (clear my work)",
        "blurb": "Empty starting point for your own diagram text",
        "examples": [
            {
                "exampleId": "blank-plain",
                "purpose": "plain",
                "minElements": 0,
                "source": "",
            },
        ],
    },
}


def catalog():
    """The catalog as a JSON-serialisable structure (contract 'Catalog shape')."""
    return {"types": [CATALOG[type_id] for type_id in ordered_type_ids()]}


def ordered_type_ids():
    return REQUIRED_TYPE_IDS + (BLANK_TYPE_ID,)


def type_ids():
    """All catalog ids including the ``blank`` pseudo-entry."""
    return tuple(CATALOG)


def entries():
    return [CATALOG[type_id] for type_id in ordered_type_ids()]


def entry_for(type_id):
    return CATALOG.get(type_id)


def label_for(type_id):
    """Human-facing label (FR-021: this wording lives in the catalog only)."""
    found = CATALOG.get(type_id)
    return found["label"] if found else None


def blurb_for(type_id):
    found = CATALOG.get(type_id)
    return found["blurb"] if found else None


def example_for(type_id, purpose="plain"):
    """First example matching ``purpose`` ('plain' or 'styled')."""
    found = CATALOG.get(type_id)
    if not found:
        return None
    for example in found["examples"]:
        if example["purpose"] == purpose:
            return example
    return None


def first_example(type_id):
    """Source handed to the editor when a starting point is picked.

    ``blank`` yields "" (the FR-023 'Clear my work' path); callers guard
    against overwriting unsaved text (FR-020). Styled example first, because
    that is the showcase the picker advertises.
    """
    if type_id == BLANK_TYPE_ID:
        return ""
    example = example_for(type_id, "styled") or example_for(type_id, "plain")
    if example is None:
        return ""
    return example["source"]


def strip_front_matter(source):
    """Remove a leading YAML front-matter block plus %%{init}%% / comment lines."""
    lines = source.splitlines(True)
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index < len(lines) and lines[index].startswith("---"):
        index += 1
        while index < len(lines) and not lines[index].startswith("---"):
            index += 1
        index += 1
    kept = []
    for line in lines[index:]:
        text = line.strip()
        if text.startswith("%%{") or text.startswith("%%"):
            continue
        kept.append(line)
    return "".join(kept)


def _first_word(body):
    """First non-blank, non-directive token of a diagram body."""
    for line in body.splitlines():
        text = line.strip()
        if not text or text.startswith("%%"):
            continue
        parts = text.split(None, 1)
        return parts[0] if parts else ""
    return ""


def detect_diagram_type(source):
    """typeId derived from the documented first keyword (pure-Python check).

    The runtime's authoritative detection stays ``ParseResult.diagramType``
    (research R-8); this rule exists so the catalog can be validated without a
    browser. Version suffixes collapse to the feature id, exactly as mermaid
    reports them (``stateDiagram-v2`` -> ``state``, ``graph`` -> ``flowchart``).
    """
    if not isinstance(source, str) or not source.strip():
        return None
    word = _first_word(strip_front_matter(source))
    if word == "graph" or word.startswith("flowchart"):
        return "flowchart"
    if word.startswith("sequenceDiagram"):
        return "sequence"
    if word.startswith("classDiagram"):
        return "class"
    if word.startswith("stateDiagram"):
        return "state"
    if word.startswith("erDiagram"):
        return "er"
    if word == "gantt":
        return "gantt"
    if word == "pie":
        return "pie"
    if word == "journey":
        return "journey"
    if word == "mindmap":
        return "mindmap"
    return None


class _Counts(object):
    """Per-type drawable-element counters (lower bounds on the source text).

    FR-018's authoritative count happens on the rendered SVG (Playwright suite);
    these pure-Python counts only guarantee an example is never a two-line toy.
    """

    @staticmethod
    def flowchart(body):
        import re
        nodes = set()
        edges = 0
        for line in _body_lines(body):
            ids = re.findall(r"([A-Za-z_][\w]*)\s*(?:\[[^\]]*\]|\([^)]*\)|\{[^}]*\})?", line)
            arrows = re.findall(r"--+>|-{2,}>|==+>|->\.|<--+>|<--", line)
            edges += len(arrows)
            for token in ids:
                nodes.add(token)
        return len(nodes), edges

    @staticmethod
    def sequence(body):
        participants = 0
        messages = 0
        for line in _body_lines(body):
            if line.startswith(("participant ", "actor ")):
                participants += 1
            elif any(arrow in line for arrow in ("->>", "-->>", "->", "-->")):
                messages += 1
        return participants, messages

    @staticmethod
    def class_(body):
        classes = 0
        relations = 0
        for line in _body_lines(body):
            if line.startswith("class "):
                classes += 1
            elif any(op in line for op in ("<|--", "..|>", "-->", "..>", "<|--",
                                           " :>")):
                relations += 1
        return classes, relations

    @staticmethod
    def state(body):
        names = set()
        edges = 0
        for line in _body_lines(body):
            if "-->" in line:
                edges += 1
                left, _, right = line.partition("-->")
                for side in (left, right):
                    token = side.split(":")[0].strip()
                    if token and not token.startswith("[*]"):
                        names.add(token.split("[")[0].split("{")[0].strip())
            elif line.startswith("state ") and "<<choice>>" not in line:
                names.add(line[6:].strip())
        return len(names), edges

    @staticmethod
    def er(body):
        import re
        entities = set()
        relations = 0
        for line in _body_lines(body):
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s+\S*--\S*\s+([A-Za-z_][A-Za-z0-9_]*)",
                             line)
            if match:
                entities.add(match.group(1))
                entities.add(match.group(2))
                relations += 1
            elif line.endswith("{"):
                entities.add(line.split()[0])
        return len(entities), relations

    @staticmethod
    def journey(body):
        sections = 0
        tasks = 0
        for line in _body_lines(body):
            if line.startswith("section "):
                sections += 1
            elif ":" in line:
                tasks += 1
        return sections, tasks

    @staticmethod
    def gantt(body):
        sections = 0
        tasks = 0
        for line in _body_lines(body):
            if line.startswith("section "):
                sections += 1
            elif line.startswith(("title", "dateFormat", "axisFormat", "todayMarker")):
                continue
            elif ":" in line:
                tasks += 1
        return sections, tasks

    @staticmethod
    def pie(body):
        import re
        slices = 0
        for line in _body_lines(body):
            if re.match(r'^("?)(?P<label>[^:]+?)\1\s*:\s*[0-9.]+$', line):
                slices += 1
        return 1, slices

    @staticmethod
    def mindmap(body):
        import re
        nodes = 0
        for line in _body_lines(body):
            if re.match(r"^(\s*)(\(\([^)]*\)\)|\[[^\]]*\]|\([^)]*\)|\{\{[^}]*\}\}|\w)", line):
                nodes += 1
        return nodes, 0


def _body_lines(body):
    return [line.strip() for line in strip_front_matter(body).splitlines() if line.strip()]


ELEMENT_COUNT_STRATEGIES = {
    "flowchart": _Counts.flowchart,
    "sequence": _Counts.sequence,
    "class": _Counts.class_,
    "state": _Counts.state,
    "er": _Counts.er,
    "journey": _Counts.journey,
    "gantt": _Counts.gantt,
    "pie": _Counts.pie,
    "mindmap": _Counts.mindmap,
}


def count_elements(source, type_id=None):
    """Lower-bound drawable element count of an example (entities + links)."""
    detected = type_id or detect_diagram_type(source)
    strategy = ELEMENT_COUNT_STRATEGIES.get(detected)
    if strategy is None:
        return 0
    entities, links = strategy(source)
    return entities + links


def select_options():
    """(typeId, label) pairs for the app's picker, in catalog order."""
    return [(item["typeId"], item["label"]) for item in entries()]


# ------------------------------------------------------------------------ --
# Front-matter / %%{init}%% extraction (contract appearance section 7 layer 1)
#
# ``appearance.resolve`` takes the parsed config as an argument, so somebody has
# to read it off the diagram text. That somebody is this module: it already owns
# "what does the user's text say about this diagram". Mermaid accepts both a
# leading ``%%{init: {...}}%%`` directive and a ``---`` front-matter block; the
# values are authored in JS shorthand (single-quoted keys), so the parse is
# deliberately tolerant: strict JSON first, then quoting repair, then give up
# with an empty dict. Bad front-matter must never break the preview -- mermaid
# itself ignores an unparsable directive, and so do we.
_INIT_PREFIX = "%%{init:"
_FM_KEYS = ("theme", "themeVariables", "lineColor", "fontSize", "fontFamily")


def _directive_json(line):
    # ``%%{init: {...}}%%`` -- the payload starts at the brace *after* the
    # ``init:`` marker, which is also where the quoted-key object begins. A
    # directive written as ``%%{{init:...}}%% with no space is the same thing.
    marker = line.index(":") + 1 if ":" in line else 0
    start = line.index("{", marker)
    depth = 0
    for index in range(start, len(line)):
        if line[index] == "{":
            depth += 1
        elif line[index] == "}":
            depth -= 1
            if depth == 0:
                return line[start:index + 1]
    return None


def _coerce_dict(text):
    """A JS-shorthand object literal as a dict, or ``{}`` if it cannot be read."""
    if not text:
        return {}
    import json as _json

    for candidate in (text, _json_quote(text)) if text else ():
        try:
            value = _json.loads(candidate)
        except ValueError:
            continue
        return value if isinstance(value, dict) else {}
    return {}


def _json_quote(text):
    """Single-quoted keys/values -> double-quoted, so ``json.loads`` can read them."""
    out = []
    in_string = None
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            if char == "\\":
                out.append(text[index:index + 2])
                index += 2
                continue
            if char == in_string:
                in_string = None
                out.append('"')
            elif char == '"':
                out.append('\\"')
            else:
                out.append(char)
        elif char in "\"'":
            in_string = char
            out.append('"')
        elif char == "'":
            in_string = "'"
            out.append('"')
        else:
            out.append(char)
        index += 1
    return "".join(out)


def _scalar(value):
    """Numbers out of a directive, strings as-is; ``'50'`` -> 50."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lstrip("-").isdigit():
            try:
                return int(stripped)
            except ValueError:
                return value
        try:
            return float(stripped)
        except ValueError:
            return value
    return value


def extract_front_matter(source):
    """The config the diagram text sets for itself (appearance contract section 7).

    Returns a dict suitable as ``appearance.resolve``'s third argument: ``theme``,
    ``themeVariables``, ``lineColor``, ``fontSize``, ``fontFamily`` and any
    diagram-family sub-object (``flowchart``, ``sequence``, ...) the directive
    names. Empty when the text has no directive, or when it has one we cannot
    read -- an unreadable directive is Mermaid's problem to ignore, not ours to
    fail on.
    """
    text = str(source or "")
    lines = text.splitlines()
    config = {}

    for line in lines[:6]:
        stripped = line.strip()
        if not stripped.startswith(_INIT_PREFIX):
            continue
        parsed = _coerce_dict(_directive_json(stripped))
        # The directive may wrap its config in an "init" key or not; accept both.
        body = parsed.get("init") if isinstance(parsed.get("init"), dict) else parsed
        for key, value in body.items():
            if key == "themeVariables" and isinstance(value, dict):
                merged = dict(config.get("themeVariables") or {})
                merged.update({k: _scalar(v) for k, v in value.items()})
                config["themeVariables"] = merged
            elif isinstance(value, dict):
                merged = dict(config.get(key) or {})
                merged.update({k: _scalar(v) for k, v in value.items()})
                config[key] = merged
            else:
                config[key] = _scalar(value)
        break

    if lines and lines[0].strip() == "---":
        index = 1
        while index < len(lines) and lines[index].strip() != "---":
            line = lines[index]
            if ":" in line and not line.startswith((" ", "\t", "#")):
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                if key:
                    if value.startswith("{"):
                        config.update({k: _scalar(v) for k, v in _coerce_dict(value).items()})
                    elif value:
                        config[key] = _scalar(value)
            index += 1

    if isinstance(config.get("theme"), str):
        config["theme"] = config["theme"].strip()
    return config
