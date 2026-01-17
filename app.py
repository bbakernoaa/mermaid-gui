import streamlit as st
import streamlit.components.v1 as components
import textwrap

st.set_page_config(page_title="Mermaid Flowchart Editor", layout="wide")

st.title("Mermaid Flowchart Editor")

templates = {
    "Basic Flowchart": """flowchart TD
    A[Start] --> B{Is it working?}
    B -- Yes --> C[Great!]
    B -- No --> D[Check logs]""",
    "Decision Tree": """flowchart TD
    A[Start] --> B{Decision?}
    B -->|Option 1| C[Outcome A]
    B -->|Option 2| D[Outcome B]
    C --> E[End]
    D --> E""",
    "Sequence Diagram": """sequenceDiagram
    Alice->>Bob: Hello Bob, how are you?
    Bob-->>Alice: I am good thanks!
    Alice-)Bob: See you later!"""
}

template_name = st.sidebar.selectbox("Choose a template", list(templates.keys()))
default_code = templates[template_name]

mermaid_code = st.text_area("Mermaid Code", value=default_code, height=300)

st.sidebar.download_button(
    label="Download .mmd source",
    data=mermaid_code,
    file_name="diagram.mmd",
    mime="text/plain"
)

st.subheader("Preview")

# Clean up mermaid code for the HTML component
# Use textwrap.dedent and then substitute into the HTML
clean_mermaid_code = textwrap.dedent(mermaid_code)

mermaid_html = f"""
<div style="margin-bottom: 10px;">
    <button onclick="downloadSVG()" style="padding: 5px 10px; cursor: pointer; margin-right: 5px;">Export SVG</button>
    <button onclick="downloadPNG()" style="padding: 5px 10px; cursor: pointer;">Export PNG</button>
</div>
<div id="mermaid-container" style="background-color: white; padding: 20px; border-radius: 10px; overflow: auto;">
    <pre class="mermaid">
{clean_mermaid_code}
    </pre>
</div>
<script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
    mermaid.initialize({{ startOnLoad: true }});

    window.downloadSVG = function() {{
        const svgElement = document.querySelector("#mermaid-container svg");
        if (!svgElement) {{
            alert("SVG not found. Please wait for the diagram to render.");
            return;
        }}
        const serializer = new XMLSerializer();
        let source = serializer.serializeToString(svgElement);
        if(!source.match(/^<svg[^>]+xmlns="http:\\/\\/www\\.w3\\.org\\/2000\\/svg"/)) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
        }}
        if(!source.match(/^<svg[^>]+xmlns:xlink="http:\\/\\/www\\.w3\\.org\\/1999\\/xlink"/)) {{
            source = source.replace(/^<svg/, '<svg xmlns:xlink="http://www.w3.org/1999/xlink"');
        }}
        const url = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(source);
        const downloadLink = document.createElement("a");
        downloadLink.href = url;
        downloadLink.download = "diagram.svg";
        document.body.appendChild(downloadLink);
        downloadLink.click();
        document.body.removeChild(downloadLink);
    }};

    window.downloadPNG = function() {{
        const svgElement = document.querySelector("#mermaid-container svg");
        if (!svgElement) {{
            alert("SVG not found. Please wait for the diagram to render.");
            return;
        }}
        const serializer = new XMLSerializer();
        const svgData = serializer.serializeToString(svgElement);
        const canvas = document.createElement("canvas");
        const svgRect = svgElement.getBoundingClientRect();

        // Increase resolution for better quality
        const scale = 2;
        canvas.width = svgRect.width * scale;
        canvas.height = svgRect.height * scale;
        const ctx = canvas.getContext("2d");

        const img = new Image();
        const svgBlob = new Blob([svgData], {{type: "image/svg+xml;charset=utf-8"}});
        const url = URL.createObjectURL(svgBlob);

        img.onload = function() {{
            ctx.fillStyle = "white";
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            URL.revokeObjectURL(url);

            const pngUrl = canvas.toDataURL("image/png");
            const downloadLink = document.createElement("a");
            downloadLink.href = pngUrl;
            downloadLink.download = "diagram.png";
            document.body.appendChild(downloadLink);
            downloadLink.click();
            document.body.removeChild(downloadLink);
        }};
        img.src = url;
    }};
</script>
"""

components.html(mermaid_html, height=600, scrolling=True)
