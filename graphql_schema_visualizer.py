"""
GraphQL Schema Visualizer — Streamlit App
Paste or upload a GraphQL schema and get an interactive visual graph.

Install dependencies:
    pip install streamlit graphviz requests

Run:
    streamlit run graphql_schema_visualizer.py
"""

import re
import json
import textwrap
import streamlit as st

# ── optional heavy deps ──────────────────────────────────────────────────────
try:
    import graphviz
    HAS_GRAPHVIZ = True
except ImportError:
    HAS_GRAPHVIZ = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ─────────────────────────────────────────────────────────────────────────────
# GraphQL SDL parser (pure Python, no external GraphQL lib needed)
# ─────────────────────────────────────────────────────────────────────────────

SCALAR_TYPES = {
    "String", "Int", "Float", "Boolean", "ID",
    "DateTime", "Date", "Time", "JSON", "UUID",
    "BigInt", "Long", "Byte", "Short", "Decimal",
}

SKIP_TYPES = {
    "Query", "Mutation", "Subscription",
    "__Schema", "__Type", "__Field", "__InputValue",
    "__EnumValue", "__Directive",
}


def strip_comments(sdl: str) -> str:
    """Remove # comments and block descriptions."""
    lines = []
    for line in sdl.splitlines():
        code = line.split("#")[0]
        lines.append(code)
    return "\n".join(lines)


def parse_schema(sdl: str) -> dict:
    """
    Lightweight SDL parser. Returns:
        {
          "types": {TypeName: {"kind": "type"|"interface"|"enum"|"input"|"union",
                               "fields": [{name, type, is_list, is_required, args}],
                               "values": [...],          # enums
                               "members": [...],         # unions
                               "implements": [...]}},
          "queries": [...],
          "mutations": [...],
        }
    """
    sdl = strip_comments(sdl)

    result = {"types": {}, "queries": [], "mutations": []}

    # Match top-level blocks
    block_re = re.compile(
        r'(type|interface|enum|input|union)\s+(\w+)'
        r'(?:\s+implements\s+([\w&\s]+?))?'
        r'\s*\{([^}]*)\}',
        re.DOTALL,
    )
    union_re = re.compile(r'union\s+(\w+)\s*=\s*([^\n]+)')
    scalar_re = re.compile(r'scalar\s+(\w+)')

    # Register scalars
    for m in scalar_re.finditer(sdl):
        SCALAR_TYPES.add(m.group(1))

    # Parse unions (they don't have braces)
    for m in union_re.finditer(sdl):
        name = m.group(1)
        members = [x.strip() for x in m.group(2).split("|") if x.strip()]
        result["types"][name] = {"kind": "union", "fields": [], "members": members, "implements": []}

    # Parse typed blocks
    for m in block_re.finditer(sdl):
        kind = m.group(1)          # type | interface | enum | input
        name = m.group(2)
        implements_raw = m.group(3) or ""
        body = m.group(4)

        if name in SKIP_TYPES:
            continue

        implements = [x.strip() for x in re.split(r'[&\s]+', implements_raw) if x.strip()]

        if kind == "enum":
            values = [v.strip() for v in body.split() if v.strip()]
            result["types"][name] = {"kind": "enum", "fields": [], "values": values, "implements": []}
            continue

        fields = parse_fields(body)
        result["types"][name] = {
            "kind": kind,
            "fields": fields,
            "implements": implements,
            "values": [],
            "members": [],
        }

        # Extract Query/Mutation operations
        if name == "Query":
            result["queries"] = [f["name"] for f in fields]
        elif name == "Mutation":
            result["mutations"] = [f["name"] for f in fields]

    return result


def parse_fields(body: str) -> list:
    """Parse fields from inside { }."""
    fields = []
    # field: name(args): Type
    field_re = re.compile(
        r'(\w+)'                    # field name
        r'(?:\([^)]*\))?'          # optional args (ignored for viz)
        r'\s*:\s*'
        r'(\[?)(\w+)(\]?)'         # type, with optional list brackets
        r'(!?)',                    # required
    )
    for m in field_re.finditer(body):
        fname = m.group(1)
        is_list = bool(m.group(2))
        ftype = m.group(3)
        is_req = bool(m.group(5))
        fields.append({
            "name": fname,
            "type": ftype,
            "is_list": is_list,
            "is_required": is_req,
        })
    return fields


# ─────────────────────────────────────────────────────────────────────────────
# Graphviz diagram builder
# ─────────────────────────────────────────────────────────────────────────────

KIND_COLORS = {
    "type":      {"bg": "#1e3a5f", "border": "#4a9eff", "font": "white"},
    "interface": {"bg": "#1e3a2f", "border": "#4aff9e", "font": "white"},
    "enum":      {"bg": "#3a1e3a", "border": "#d44aff", "font": "white"},
    "input":     {"bg": "#3a2a1e", "border": "#ffaa4a", "font": "white"},
    "union":     {"bg": "#2a1e3a", "border": "#ff4a9e", "font": "white"},
}


def build_graph(schema: dict, show_scalars: bool, show_enums: bool,
                filter_types: set | None = None) -> "graphviz.Digraph":
    dot = graphviz.Digraph(
        name="GraphQL Schema",
        graph_attr={
            "rankdir": "LR",
            "splines": "polyline",
            "nodesep": "0.6",
            "ranksep": "1.2",
            "bgcolor": "#0d1117",
            "fontname": "Courier New",
        },
        node_attr={
            "fontname": "Courier New",
            "fontsize": "11",
            "shape": "none",
            "margin": "0",
        },
        edge_attr={
            "fontname": "Courier New",
            "fontsize": "9",
            "color": "#4a9eff88",
            "fontcolor": "#aaaaaa",
        },
    )

    types = schema["types"]
    visible = set()

    for tname, tdef in types.items():
        if filter_types and tname not in filter_types:
            continue
        if tdef["kind"] == "enum" and not show_enums:
            continue
        visible.add(tname)

    for tname in visible:
        tdef = types[tname]
        kind = tdef["kind"]
        colors = KIND_COLORS.get(kind, KIND_COLORS["type"])

        if kind == "enum":
            values_html = "".join(
                f'<TR><TD ALIGN="LEFT" BGCOLOR="#2a1a2a" '
                f'COLOR="{colors["border"]}" BORDER="0" CELLPADDING="3">'
                f'<FONT COLOR="#d44aff">◆ {v}</FONT></TD></TR>'
                for v in tdef["values"]
            )
            label = (
                f'<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" '
                f'BGCOLOR="{colors["bg"]}" COLOR="{colors["border"]}" STYLE="ROUNDED">'
                f'<TR><TD BGCOLOR="{colors["border"]}" ALIGN="CENTER" CELLPADDING="5">'
                f'<FONT COLOR="white"><B>{tname}</B></FONT>'
                f'<FONT COLOR="#ffffffaa"> «enum»</FONT></TD></TR>'
                f'{values_html}'
                f'</TABLE>>'
            )
        elif kind == "union":
            members_html = "".join(
                f'<TR><TD ALIGN="LEFT" BGCOLOR="#1e1a2a" '
                f'COLOR="{colors["border"]}" BORDER="0" CELLPADDING="3">'
                f'<FONT COLOR="#ff4a9e">| {m}</FONT></TD></TR>'
                for m in tdef["members"]
            )
            label = (
                f'<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" '
                f'BGCOLOR="{colors["bg"]}" COLOR="{colors["border"]}" STYLE="ROUNDED">'
                f'<TR><TD BGCOLOR="{colors["border"]}" ALIGN="CENTER" CELLPADDING="5">'
                f'<FONT COLOR="white"><B>{tname}</B></FONT>'
                f'<FONT COLOR="#ffffffaa"> «union»</FONT></TD></TR>'
                f'{members_html}'
                f'</TABLE>>'
            )
        else:
            badge = {"interface": " «interface»", "input": " «input»"}.get(kind, "")
            rows = ""
            for f in tdef["fields"]:
                ft = f["type"]
                is_scalar = ft in SCALAR_TYPES or ft not in types
                fc = "#aaddff" if is_scalar else "#4aff9e"
                list_marker = "[ ]" if f["is_list"] else "   "
                req_marker = "!" if f["is_required"] else " "
                rows += (
                    f'<TR>'
                    f'<TD ALIGN="LEFT" BGCOLOR="#0d1a2a" BORDER="0" CELLPADDING="3">'
                    f'<FONT COLOR="#e0e0e0">{f["name"]}</FONT></TD>'
                    f'<TD ALIGN="LEFT" BGCOLOR="#0d1a2a" BORDER="0" CELLPADDING="3">'
                    f'<FONT COLOR="{fc}">{list_marker} {ft}{req_marker}</FONT></TD>'
                    f'</TR>'
                )
            label = (
                f'<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" '
                f'BGCOLOR="{colors["bg"]}" COLOR="{colors["border"]}" STYLE="ROUNDED">'
                f'<TR><TD COLSPAN="2" BGCOLOR="{colors["border"]}" ALIGN="CENTER" CELLPADDING="5">'
                f'<FONT COLOR="white"><B>{tname}</B></FONT>'
                f'<FONT COLOR="#ffffffcc">{badge}</FONT></TD></TR>'
                f'{rows or "<TR><TD><FONT COLOR=\'#666\'> (no fields) </FONT></TD></TR>"}'
                f'</TABLE>>'
            )

        dot.node(tname, label=label)

    # Edges
    for tname in visible:
        tdef = types[tname]
        for f in tdef["fields"]:
            ft = f["type"]
            if ft in visible:
                label = f['name'] + ("[]" if f["is_list"] else "")
                dot.edge(tname, ft, label=label,
                         arrowhead="vee" if not f["is_list"] else "crow")
        for iface in tdef.get("implements", []):
            if iface in visible:
                dot.edge(tname, iface, style="dashed", arrowhead="empty",
                         color="#4aff9e55", label="implements")
        for m in tdef.get("members", []):
            if m in visible:
                dot.edge(tname, m, style="dotted", arrowhead="odot",
                         color="#ff4a9e55")

    return dot


# ─────────────────────────────────────────────────────────────────────────────
# Introspection query (for live endpoint)
# ─────────────────────────────────────────────────────────────────────────────

INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    types {
      kind name
      fields(includeDeprecated: true) {
        name
        type { ...TypeRef }
      }
      inputFields { name type { ...TypeRef } }
      interfaces { name }
      enumValues(includeDeprecated: true) { name }
      possibleTypes { name }
    }
  }
}
fragment TypeRef on __Type {
  kind name
  ofType { kind name ofType { kind name ofType { kind name } } }
}
"""


def introspection_to_sdl_dict(data: dict) -> dict:
    """Convert introspection JSON to our internal schema dict."""
    schema = {"types": {}, "queries": [], "mutations": []}
    raw_types = data.get("data", {}).get("__schema", {}).get("types", [])

    def unwrap(t):
        """Unwrap NonNull/List to get base type name and list flag."""
        is_list = False
        while t and t.get("kind") in ("NON_NULL", "LIST"):
            if t["kind"] == "LIST":
                is_list = True
            t = t.get("ofType")
        return (t or {}).get("name", ""), is_list

    for t in raw_types:
        name = t["name"]
        if not name or name.startswith("__") or name in SKIP_TYPES:
            continue
        kind_map = {
            "OBJECT": "type", "INTERFACE": "interface",
            "ENUM": "enum", "INPUT_OBJECT": "input", "UNION": "union",
        }
        kind = kind_map.get(t["kind"])
        if not kind:
            continue

        fields = []
        for f in (t.get("fields") or []) + (t.get("inputFields") or []):
            btype, is_list = unwrap(f["type"])
            fields.append({"name": f["name"], "type": btype,
                           "is_list": is_list, "is_required": False})

        values = [e["name"] for e in (t.get("enumValues") or [])]
        members = [p["name"] for p in (t.get("possibleTypes") or [])]
        implements = [i["name"] for i in (t.get("interfaces") or [])]

        schema["types"][name] = {
            "kind": kind, "fields": fields, "values": values,
            "members": members, "implements": implements,
        }

    return schema


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit UI
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="GraphQL Schema Visualizer",
    page_icon="🔭",
    layout="wide",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Space+Grotesk:wght@300;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Space Grotesk', sans-serif;
    background-color: #0d1117;
    color: #e0e0e0;
}
.stApp { background-color: #0d1117; }
h1 { font-weight: 700; letter-spacing: -1px; color: #4a9eff; }
.stTextArea textarea {
    background: #161b22 !important;
    color: #c9d1d9 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
    border: 1px solid #30363d !important;
}
.stButton > button {
    background: linear-gradient(135deg, #1f6feb, #4a9eff);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    padding: 0.5rem 2rem;
}
.stButton > button:hover { opacity: 0.85; }
.metric-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 1rem 1.5rem;
    text-align: center;
}
.metric-val { font-size: 2rem; font-weight: 700; color: #4a9eff; }
.metric-lbl { font-size: 0.8rem; color: #888; text-transform: uppercase; letter-spacing: 1px; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; margin-right: 16px; }
.legend-dot {
    width: 12px; height: 12px; border-radius: 3px; display: inline-block;
}
</style>
""", unsafe_allow_html=True)

st.markdown("# 🔭 GraphQL Schema Visualizer")
st.markdown("*Paste SDL, upload a `.graphql` file, or point to a live endpoint — get an instant ER diagram.*")
st.divider()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Options")
    show_enums   = st.toggle("Show enums", value=True)
    show_scalars = st.toggle("Show scalar edges", value=False)
    layout_dir   = st.selectbox("Layout direction", ["LR (left→right)", "TB (top→bottom)", "RL", "BT"])
    rankdir      = layout_dir.split()[0]
    st.divider()
    st.markdown("### 🎨 Legend")
    st.markdown("""
<div>
  <span class='legend-item'><span class='legend-dot' style='background:#1e3a5f;border:2px solid #4a9eff'></span>Type</span>
  <span class='legend-item'><span class='legend-dot' style='background:#1e3a2f;border:2px solid #4aff9e'></span>Interface</span>
  <span class='legend-item'><span class='legend-dot' style='background:#3a1e3a;border:2px solid #d44aff'></span>Enum</span>
  <span class='legend-item'><span class='legend-dot' style='background:#3a2a1e;border:2px solid #ffaa4a'></span>Input</span>
  <span class='legend-item'><span class='legend-dot' style='background:#2a1e3a;border:2px solid #ff4a9e'></span>Union</span>
</div>
""", unsafe_allow_html=True)
    st.divider()
    st.markdown("### ℹ️ Tips")
    st.markdown("""
- **Solid arrows** = object references  
- **Crow-foot arrows** = list relations  
- **Dashed arrows** = interface impl  
- **Dotted arrows** = union members  
    """)

# ── Input tabs ────────────────────────────────────────────────────────────────
tab_sdl, tab_file, tab_url = st.tabs(["📝 Paste SDL", "📂 Upload File", "🌐 Live Endpoint"])

sdl_text  = ""
schema    = None
error_msg = ""

EXAMPLE_SCHEMA = textwrap.dedent("""
type User {
  id: ID!
  name: String!
  email: String!
  role: Role!
  posts: [Post!]!
  profile: Profile
}

type Profile {
  id: ID!
  bio: String
  avatarUrl: String
  user: User!
}

type Post {
  id: ID!
  title: String!
  content: String!
  published: Boolean!
  author: User!
  tags: [Tag!]!
  comments: [Comment!]!
  createdAt: DateTime
}

type Comment {
  id: ID!
  body: String!
  author: User!
  post: Post!
}

type Tag {
  id: ID!
  name: String!
  posts: [Post!]!
}

enum Role {
  ADMIN
  EDITOR
  VIEWER
}

interface Node {
  id: ID!
}

input CreatePostInput {
  title: String!
  content: String!
  tagIds: [ID!]
}
""").strip()

with tab_sdl:
    sdl_text = st.text_area(
        "GraphQL SDL",
        value=EXAMPLE_SCHEMA,
        height=320,
        placeholder="Paste your schema here…",
        label_visibility="collapsed",
    )

with tab_file:
    uploaded = st.file_uploader("Upload .graphql or .gql file", type=["graphql", "gql", "txt"])
    if uploaded:
        sdl_text = uploaded.read().decode("utf-8")
        st.success(f"Loaded `{uploaded.name}` ({len(sdl_text):,} chars)")

with tab_url:
    endpoint = st.text_input("GraphQL Endpoint URL", placeholder="https://api.example.com/graphql")
    headers_raw = st.text_area("Headers (JSON, optional)", value='{"Authorization": "Bearer <token>"}', height=80)
    if st.button("🔍 Introspect Endpoint"):
        if not HAS_REQUESTS:
            st.error("`requests` library not installed. Run: `pip install requests`")
        else:
            try:
                hdrs = json.loads(headers_raw) if headers_raw.strip() else {}
                hdrs["Content-Type"] = "application/json"
                resp = requests.post(
                    endpoint,
                    json={"query": INTROSPECTION_QUERY},
                    headers=hdrs,
                    timeout=15,
                )
                resp.raise_for_status()
                schema = introspection_to_sdl_dict(resp.json())
                st.success(f"Introspected {len(schema['types'])} types from endpoint.")
            except Exception as e:
                error_msg = str(e)

# ── Parse SDL if schema not already set ──────────────────────────────────────
if schema is None and sdl_text.strip():
    try:
        schema = parse_schema(sdl_text)
    except Exception as e:
        error_msg = str(e)

# ── Display errors ────────────────────────────────────────────────────────────
if error_msg:
    st.error(f"**Error:** {error_msg}")

# ── Main content ──────────────────────────────────────────────────────────────
if schema and schema["types"]:
    types = schema["types"]
    n_types      = sum(1 for t in types.values() if t["kind"] == "type")
    n_interfaces = sum(1 for t in types.values() if t["kind"] == "interface")
    n_enums      = sum(1 for t in types.values() if t["kind"] == "enum")
    n_inputs     = sum(1 for t in types.values() if t["kind"] == "input")
    n_unions     = sum(1 for t in types.values() if t["kind"] == "union")
    total_fields = sum(len(t["fields"]) for t in types.values())

    # Metrics row
    cols = st.columns(6)
    metrics = [
        ("Types", n_types),
        ("Interfaces", n_interfaces),
        ("Enums", n_enums),
        ("Inputs", n_inputs),
        ("Unions", n_unions),
        ("Total Fields", total_fields),
    ]
    for col, (lbl, val) in zip(cols, metrics):
        with col:
            st.markdown(
                f'<div class="metric-card"><div class="metric-val">{val}</div>'
                f'<div class="metric-lbl">{lbl}</div></div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # Type filter
    all_type_names = sorted(types.keys())
    selected = st.multiselect(
        "Filter types (leave empty = show all)",
        options=all_type_names,
        default=[],
    )
    filter_set = set(selected) if selected else None

    # Build & render graph
    if not HAS_GRAPHVIZ:
        st.warning("The `graphviz` Python package is not installed. Run: `pip install graphviz`")
        st.info("Also ensure the Graphviz system package is installed: https://graphviz.org/download/")
    else:
        try:
            dot = build_graph(schema, show_scalars=show_scalars, show_enums=show_enums,
                              filter_types=filter_set)
            dot.graph_attr["rankdir"] = rankdir.split()[0]
            st.graphviz_chart(dot.source, use_container_width=True)
        except Exception as e:
            st.error(f"Rendering error: {e}")
            st.code(str(e))

    # ── Schema table view ─────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 📋 Schema Details")

    search = st.text_input("🔍 Search types / fields", placeholder="e.g. User, email, Post…")

    for tname in sorted(types.keys()):
        tdef = types[tname]
        if filter_set and tname not in filter_set:
            continue
        if search and search.lower() not in tname.lower() and \
                not any(search.lower() in f["name"].lower() for f in tdef["fields"]):
            continue

        badge_color = {
            "type": "🔵", "interface": "🟢", "enum": "🟣",
            "input": "🟠", "union": "🩷",
        }.get(tdef["kind"], "⚪")

        with st.expander(f"{badge_color} **{tname}** `{tdef['kind']}`  —  {len(tdef['fields'])} fields"):
            if tdef["kind"] == "enum":
                st.markdown("**Values:** " + ", ".join(f"`{v}`" for v in tdef["values"]))
            elif tdef["kind"] == "union":
                st.markdown("**Members:** " + ", ".join(f"`{m}`" for m in tdef["members"]))
            else:
                if tdef["implements"]:
                    st.markdown("**Implements:** " + ", ".join(f"`{i}`" for i in tdef["implements"]))
                if tdef["fields"]:
                    rows = []
                    for f in tdef["fields"]:
                        tstr = f"[{f['type']}]" if f["is_list"] else f["type"]
                        req  = "✓" if f["is_required"] else ""
                        rows.append({"Field": f["name"], "Type": tstr, "Required": req})
                    st.table(rows)
                else:
                    st.markdown("*No fields*")

    # ── Operations summary ────────────────────────────────────────────────────
    if schema["queries"] or schema["mutations"]:
        st.divider()
        q_col, m_col = st.columns(2)
        with q_col:
            st.markdown("### 🔵 Queries")
            for q in schema["queries"]:
                st.markdown(f"- `{q}`")
        with m_col:
            st.markdown("### 🟠 Mutations")
            for m in schema["mutations"]:
                st.markdown(f"- `{m}`")

elif not error_msg:
    st.info("👆 Paste a GraphQL schema or upload a file to get started. A sample schema is pre-loaded above.")

st.divider()
st.caption("GraphQL Schema Visualizer • Built with Streamlit + Graphviz")
