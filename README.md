# Mermaid Flowchart GUI

An interactive web-based editor for Mermaid flowcharts, built with Python (Streamlit) and served entirely in the browser using Stlite.

## Features

- **Live Preview:** Real-time rendering of Mermaid flowchart code.
- **Templates:** Quickly start with Basic Flowchart, Decision Tree, or Sequence Diagram templates.
- **Save & Export:**
  - Download raw `.mmd` source code.
  - Export as high-quality **SVG**.
  - Export as **PNG** (with white background).
- **Zero Server Setup:** Runs entirely on the client side via WebAssembly (Stlite).

## How to Use

1. Enter your Mermaid code in the text area.
2. The preview will automatically update below.
3. Use the sidebar to switch between templates or download the source code.
4. Use the "Export SVG" or "Export PNG" buttons in the preview area to save the diagram to your computer.

## Deployment to GitHub Pages

This project is designed to be hosted on GitHub Pages without any backend server.

1. Push `app.py` and `index.html` to your GitHub repository.
2. Go to **Settings > Pages** in your repository.
3. Select the branch (e.g., `main`) and folder (e.g., `/root`) to serve from.
4. Save the settings. Your GUI will be available at `https://<your-username>.github.io/<repo-name>/`.

## Local Development

To run the application locally for testing:

```bash
python3 -m http.server 8000
```

Then open `http://localhost:8000` in your web browser.
