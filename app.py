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
    import {{ Canvg }} from 'https://cdn.jsdelivr.net/npm/canvg@4.0.1/+esm';

    // Force SVG labels instead of HTML labels for better compatibility with export tools
    mermaid.initialize({{
        startOnLoad: true,
        htmlLabels: false,
        flowchart: {{ useHtmlLabels: false, htmlLabels: false }},
        sequence: {{ useHtmlLabels: false }},
        gantt: {{ useHtmlLabels: false }}
    }});

    window.getSerializedSVG = function(sourceSvg) {{
        const clone = sourceSvg.cloneNode(true);

        // Ensure absolute dimensions for consistency in tools like canvg
        const viewBox = sourceSvg.viewBox.baseVal;
        const width = viewBox.width || sourceSvg.clientWidth || 800;
        const height = viewBox.height || sourceSvg.clientHeight || 600;

        clone.setAttribute("width", width);
        clone.setAttribute("height", height);
        clone.setAttribute("xml:space", "preserve");
        clone.setAttribute("text-rendering", "geometricPrecision");

        // Function to inline styles
        function inlineStyles(source, target) {{
            const computedStyle = window.getComputedStyle(source);
            const relevantProps = [
                'fill', 'fill-opacity', 'fill-rule',
                'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'stroke-dasharray', 'stroke-opacity',
                'font-family', 'font-size', 'font-weight', 'font-style', 'letter-spacing', 'word-spacing',
                'text-anchor', 'dominant-baseline',
                'opacity', 'visibility', 'display',
                'stop-color', 'stop-opacity',
                'marker-start', 'marker-end', 'marker-mid'
            ];

            for (const prop of relevantProps) {{
                const value = computedStyle.getPropertyValue(prop);
                if (value) {{
                    // Ensure marker URLs are relative
                    if (prop.startsWith('marker') && value.includes('url(')) {{
                        // Match everything after the last # inside the url()
                        const match = value.match(/url\\(["']?.*?(#[^"\\)]+)["']?\\)/);
                        if (match) {{
                            target.style[prop] = `url(${{match[1]}})`;
                            continue;
                        }}
                    }}
                    target.style[prop] = value;
                }}
            }}

            // Special handling for background-color -> fill (for nodes/clusters)
            const fill = computedStyle.getPropertyValue('fill');
            const bgColor = computedStyle.getPropertyValue('background-color');
            if ((!fill || fill === 'none' || fill === 'transparent' || fill === 'rgba(0, 0, 0, 0)') &&
                bgColor && bgColor !== 'rgba(0, 0, 0, 0)' && bgColor !== 'transparent') {{
                target.style.fill = bgColor;
            }}
        }}

        // Apply styles recursively
        const allSourceElements = sourceSvg.querySelectorAll('*');
        const allCloneElements = clone.querySelectorAll('*');

        for (let i = 0; i < allSourceElements.length; i++) {{
            const sourceEl = allSourceElements[i];
            const cloneEl = allCloneElements[i];
            inlineStyles(sourceEl, cloneEl);

            // Explicitly preserve space on text and tspan elements
            const tagName = sourceEl.tagName.toLowerCase();
            if (tagName === 'text' || tagName === 'tspan') {{
                cloneEl.setAttribute("xml:space", "preserve");
            }}
        }}

        // Remove internal style tags to avoid conflicts
        const internalStyles = clone.querySelectorAll('style');
        internalStyles.forEach(s => s.remove());

        // Add a minimal style for text white-space
        const styleElement = document.createElementNS("http://www.w3.org/2000/svg", "style");
        styleElement.textContent = "text, tspan {{ white-space: pre; }}";
        clone.prepend(styleElement);

        const serializer = new XMLSerializer();
        let source = serializer.serializeToString(clone);

        // Clean up any absolute URLs that might have sneaked in during serialization
        // Matches url("http://...#id") or url(http://...#id)
        // Replaces with url(#id)
        source = source.replace(/url\\(["']?https?:\\/\\/[^#^"^'^\\)]+(#[^"\\)^']+?)["']?\\)/g, 'url($1)');

        if(!source.match(/^<svg[^>]+xmlns="http:\\/\\/www\\.w3\\.org\\/2000\\/svg"/)) {{
            source = source.replace(/^<svg/, '<svg xmlns="http://www.w3.org/2000/svg"');
        }}
        if(!source.match(/^<svg[^>]+xmlns:xlink="http:\\/\\/www\\.w3\\.org\\/1999\\/xlink"/)) {{
            source = source.replace(/^<svg/, '<svg xmlns:xlink="http://www.w3.org/1999/xlink"');
        }}
        return source;
    }};

    window.downloadSVG = function() {{
        const svgElement = document.querySelector("#mermaid-container svg");
        if (!svgElement) {{
            alert("SVG not found. Please wait for the diagram to render.");
            return;
        }}

        const source = window.getSerializedSVG(svgElement);
        const url = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(source);
        const downloadLink = document.createElement("a");
        downloadLink.href = url;
        downloadLink.download = "diagram.svg";
        document.body.appendChild(downloadLink);
        downloadLink.click();
        document.body.removeChild(downloadLink);
    }};

    window.downloadPNG = async function() {{
        const svgElement = document.querySelector("#mermaid-container svg");
        if (!svgElement) {{
            alert("SVG not found. Please wait for the diagram to render.");
            return;
        }}

        const viewBox = svgElement.viewBox.baseVal;
        const width = viewBox.width || svgElement.clientWidth;
        const height = viewBox.height || svgElement.clientHeight;

        const svgData = window.getSerializedSVG(svgElement);
        const canvas = document.createElement("canvas");

        // Increase resolution for high-quality export
        const scale = 3;
        canvas.width = width * scale;
        canvas.height = height * scale;
        const ctx = canvas.getContext("2d");

        // Fill background with white
        ctx.fillStyle = "white";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const v = await Canvg.from(ctx, svgData);
        await v.render({{
            ignoreMouse: true,
            ignoreAnimation: true,
            scale: scale
        }});

        const pngUrl = canvas.toDataURL("image/png", 1.0);
        const downloadLink = document.createElement("a");
        downloadLink.href = pngUrl;
        downloadLink.download = "diagram.png";
        document.body.appendChild(downloadLink);
        downloadLink.click();
        document.body.removeChild(downloadLink);
    }};
</script>
"""

components.html(mermaid_html, height=600, scrolling=True)
