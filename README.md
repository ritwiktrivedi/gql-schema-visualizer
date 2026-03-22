# 🔭 GraphQL Schema Visualizer

An interactive tool to automatically visualize any GraphQL schema as an ER diagram — paste SDL, upload a file, or introspect a live endpoint.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io)

---

## ✨ Features

- **3 input modes** — paste SDL, upload `.graphql`/`.gql`, or introspect a live endpoint
- **Interactive ER diagram** — color-coded nodes by kind, directional relationship arrows
- **Type filter** — focus on a subset of types
- **Schema table view** — searchable, expandable per-type field breakdown
- **Metrics bar** — counts for types, interfaces, enums, inputs, unions, and total fields
- **Query / Mutation summary** — lists all root operations

## 🗂️ Repo Structure

```
├── graphql_schema_visualizer.py   # Main Streamlit app
├── requirements.txt               # Python dependencies
├── packages.txt                   # System dependencies (Graphviz binary)
└── README.md
```

## 🚀 Deploy to Streamlit Cloud

1. **Fork or push** this repo to your GitHub account.
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **"New app"** → select your repo → set:
   - **Branch:** `main`
   - **Main file path:** `graphql_schema_visualizer.py`
4. Click **"Deploy"** — that's it!

Streamlit Cloud automatically reads `requirements.txt` (Python packages) and `packages.txt` (apt packages, needed for the Graphviz binary).

## 🏃 Run Locally

```bash
# Install system graphviz (macOS)
brew install graphviz

# Install system graphviz (Ubuntu/Debian)
sudo apt-get install graphviz

# Install Python deps
pip install -r requirements.txt

# Run
streamlit run graphql_schema_visualizer.py
```

## 🎨 Node Color Legend

| Color  | Kind       |
|--------|------------|
| 🔵 Blue     | `type`      |
| 🟢 Green    | `interface` |
| 🟣 Purple   | `enum`      |
| 🟠 Orange   | `input`     |
| 🩷 Pink     | `union`     |

## 🔗 Arrow Types

| Style   | Meaning                  |
|---------|--------------------------|
| Solid → | Single object reference  |
| Crow-foot → | List relation       |
| Dashed  | `implements` interface   |
| Dotted  | Union member             |

## 📄 License

MIT
