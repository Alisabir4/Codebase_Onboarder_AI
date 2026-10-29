"""Build a self-contained, interactive PyVis architecture graph."""
from __future__ import annotations

import html as html_lib
import json
import os
from pathlib import PurePosixPath

from pyvis.network import Network


def _module_name(path: str) -> str:
    name = path[:-3] if path.endswith(".py") else path
    name = name.replace("/", ".").replace("\\", ".")
    if name.endswith(".__init__"):
        name = name[:-9]
    return name.strip(".")


def _json_safe(value):
    """Return a JSON-compatible copy of arbitrary graph metadata."""
    if isinstance(value, (PurePosixPath, os.PathLike)):
        return str(value)
    if isinstance(value, dict):
        return {str(_json_safe(key)): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _package(path: str) -> str:
    parts = PurePosixPath(path).parts[:-1]
    if parts and parts[0] in {"src", "app", "lib"}:
        parts = parts[1:]
    return parts[0] if parts else "Root"


def _layer(path: str) -> str:
    """Infer a broad layer only from recognizable directory names."""
    parts = {part.lower().replace("-", "_") for part in PurePosixPath(path).parts[:-1]}
    labels = {
        "Presentation (inferred)": {"api", "routes", "views", "pages", "ui", "components", "controllers"},
        "Domain (inferred)": {"domain", "models", "entities"},
        "Services (inferred)": {"services", "use_cases", "usecases"},
        "Data (inferred)": {"data", "db", "repositories", "persistence"},
        "Infrastructure (inferred)": {"infrastructure", "infra", "adapters"},
        "Utilities (inferred)": {"utils", "common", "helpers"},
    }
    return next((label for label, names in labels.items() if parts & names), "Unclassified")


def resolve_local_dependencies(modules: dict) -> set[tuple[str, str]]:
    """Resolve static imports only when they map unambiguously to known modules."""
    normalized = {str(path): data for path, data in modules.items()}
    names: dict[str, list[str]] = {}
    basenames: dict[str, list[str]] = {}
    for path in normalized:
        names.setdefault(_module_name(path), []).append(path)
        basenames.setdefault(PurePosixPath(path).stem, []).append(path)

    edges = set()
    for path, data in normalized.items():
        imports = set(data.get("imports", [])) | set(data.get("local_imports", []))
        for imported in imports:
            matches = []
            if imported.startswith("."):
                module_name = _module_name(path)
                package = module_name.rsplit(".", 1)[0] if "." in module_name else ""
                level = len(imported) - len(imported.lstrip("."))
                base = package.split(".") if package else []
                if level > 1:
                    base = base[:max(0, len(base) - level + 1)]
                suffix = imported.lstrip(".")
                candidate = ".".join([*base, suffix] if suffix else base)
                parts = candidate.split(".") if candidate else []
            else:
                parts = imported.split(".") if imported else []

            # Prefer the longest known module prefix. Do not pick among duplicate
            # canonical names (for example both pkg.py and pkg/__init__.py).
            for end in range(len(parts), 0, -1):
                found = names.get(".".join(parts[:end]), [])
                if found:
                    matches = found if len(found) == 1 else []
                    break
            if not matches and not imported.startswith(".") and len(parts) == 1:
                found = basenames.get(imported, [])
                if len(found) == 1:
                    matches = found
            for target in matches:
                if target != path:
                    edges.add((path, target))
    return edges


def _controls(packages: list[str], layers: list[str]) -> str:
    def options(values):
        return "".join(f'<option value="{html_lib.escape(value, quote=True)}">{html_lib.escape(value)}</option>'
                       for value in values)
    return f"""
    <div id="cb-toolbar" role="toolbar" aria-label="Architecture graph controls">
      <input id="cb-search" type="search" placeholder="Search modules" aria-label="Search modules">
      <select id="cb-package" aria-label="Filter package"><option value="">All packages</option>{options(packages)}</select>
      <select id="cb-layer" aria-label="Filter inferred layer"><option value="">All layers</option>{options(layers)}</select>
      <button id="cb-reset" type="button">Reset view</button>
      <button id="cb-export" type="button">Export graph JSON</button>
      <span id="cb-search-status" aria-live="polite"></span>
    </div>
    <div id="cb-details" aria-live="polite"><strong>Select a module</strong><span>Direct dependencies and dependents will be highlighted.</span></div>
    <style>
      #cb-toolbar {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; padding:12px; background:#0d1425; border:1px solid #263653; border-radius:12px; color:#e8eefc; }}
      #cb-toolbar input,#cb-toolbar select,#cb-toolbar button {{ color:#e8eefc; background:#151f34; border:1px solid #354667; border-radius:7px; padding:8px 10px; font:13px Inter,Arial,sans-serif; }}
      #cb-toolbar input {{ flex:1 1 180px; min-width:140px; }}
      #cb-toolbar button {{ cursor:pointer; }}
      #cb-toolbar button:hover {{ border-color:#8b7bff; }}
      #cb-search-status {{ color:#9aabc7; font:12px Inter,Arial,sans-serif; padding:0 4px; }}
      #cb-details {{ margin:10px 0; padding:12px 14px; min-height:58px; color:#dce5f7; background:#0d1425; border:1px solid #263653; border-radius:12px; font:13px Inter,Arial,sans-serif; }}
      #cb-details strong {{ display:block; color:#fff; margin-bottom:6px; }}
      #cb-details span {{ display:block; color:#aab8d0; line-height:1.5; }}
      #cb-details code {{ color:#c6bfff; }}
    </style>
    """


_INTERACTION_SCRIPT = r"""
<script>
(function () {
  const search = document.getElementById('cb-search');
  const packageFilter = document.getElementById('cb-package');
  const layerFilter = document.getElementById('cb-layer');
  const details = document.getElementById('cb-details');
  if (!window.network || !window.nodes || !window.edges) return;
  const base = new Map(nodes.get().map(n => [String(n.id), {color:n.color, hidden:false}]));
  let resetting = false;

  function applyFilters() {
    const q = search.value.trim().toLowerCase();
    const pkg = packageFilter.value;
    const layer = layerFilter.value;
    const visible = [];
    nodes.get().forEach(n => {
      const match = (!q || String(n.label).toLowerCase().includes(q) || String(n.id).toLowerCase().includes(q))
        && (!pkg || n.package === pkg) && (!layer || n.layer === layer);
      n.hidden = !match;
      if (match) visible.push(n.id);
    });
    const visibleIds = new Set(visible.map(String));
    edges.get().forEach(e => { e.hidden=!(visibleIds.has(String(e.from)) && visibleIds.has(String(e.to))); });
    nodes.update(nodes.get());
    edges.update(edges.get());
    document.getElementById('cb-search-status').textContent=visible.length ? `${visible.length} module${visible.length===1?'':'s'} shown` : 'No matching modules';
    if (visible.length) network.fit({nodes:visible, animation:{duration:250, easingFunction:'easeInOutQuad'}});
  }

  function reset() {
    if (resetting) return;
    resetting = true;
    nodes.get().forEach(n => { const original=base.get(String(n.id)); n.hidden=false; n.color=original.color; });
    edges.get().forEach(e => { e.hidden=false; e.color={color:'#526789', highlight:'#9d8cff'}; });
    nodes.update(nodes.get()); edges.update(edges.get());
    search.value=''; packageFilter.value=''; layerFilter.value='';
    document.getElementById('cb-search-status').textContent='';
    network.unselectAll(); network.fit({animation:{duration:300, easingFunction:'easeInOutQuad'}});
    details.innerHTML='<strong>Select a module</strong><span>Direct dependencies and dependents will be highlighted.</span>';
    resetting = false;
  }

  [search,packageFilter,layerFilter].forEach(el => el.addEventListener(el===search?'input':'change', applyFilters));
  document.getElementById('cb-reset').addEventListener('click', reset);
  document.getElementById('cb-export').addEventListener('click', () => {
    const data={nodes:nodes.get().map(n=>({id:n.id,label:n.label,module:n.module,package:n.package,layer:n.layer,symbols:n.symbols,imports:n.imports})),
      edges:edges.get().map(e=>({from:e.from,to:e.to}))};
    const link=document.createElement('a'); link.href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
    link.download='architecture-graph.json'; link.click(); URL.revokeObjectURL(link.href);
  });
  network.on('selectNode', params => {
    const selected=nodes.get(params.nodes[0]); if(!selected) return;
    const outgoing=edges.get({filter:e=>String(e.from)===String(selected.id)}).map(e=>String(e.to));
    const incoming=edges.get({filter:e=>String(e.to)===String(selected.id)}).map(e=>String(e.from));
    const direct=new Set([String(selected.id),...outgoing,...incoming]);
    nodes.get().forEach(n => { if(!n.hidden) n.color=direct.has(String(n.id)) ? (String(n.id)===String(selected.id)?'#8b7bff':(outgoing.includes(String(n.id))?'#20b8a6':'#4f9cf9')) : 'rgba(150,165,190,0.22)'; });
    edges.get().forEach(e => { e.color=(String(e.from)===String(selected.id)||String(e.to)===String(selected.id))?'#a69bff':'rgba(82,103,137,0.16)'; });
    nodes.update(nodes.get()); edges.update(edges.get());
    const list=(title,values)=>`<strong>${title}</strong><span>${values.length?values.map(v=>`<code>${String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}</code>`).join(' · '):'None detected'}</span>`;
    details.innerHTML='';
    const heading=document.createElement('strong'); heading.textContent=selected.module+' · '+selected.layer; details.appendChild(heading);
    details.insertAdjacentHTML('beforeend',list('Direct dependencies',outgoing));
    details.insertAdjacentHTML('beforeend',list('Dependents',incoming));
    details.insertAdjacentHTML('beforeend',list('Functions and classes',(selected.symbols||[]).map(s=>`${s.kind} ${s.name} (line ${s.line})`)));
    details.insertAdjacentHTML('beforeend',list('Imports',selected.imports||[]));
  });
  network.on('deselectNode', () => { if(!resetting && !search.value && !packageFilter.value && !layerFilter.value) reset(); });
})();
</script>
"""


def build_interactive_graph(modules: dict):
    normalized = {str(path): _json_safe(data) for path, data in modules.items()}
    links = resolve_local_dependencies(normalized)
    packages = sorted({_package(path) for path in normalized})
    layers = sorted({_layer(path) for path in normalized})
    net = Network(height="620px", width="100%", directed=True, bgcolor="#0b1020",
                  font_color="#e8eefc", neighborhood_highlight=False,
                  select_menu=False, filter_menu=False, cdn_resources="in_line")
    net.set_options("""
    {"nodes":{"shape":"dot","size":18,"font":{"size":14,"face":"Inter, Arial","color":"#e8eefc"},"borderWidth":1,"shadow":{"enabled":true,"color":"rgba(0,0,0,0.25)","size":10,"x":0,"y":3}},
     "edges":{"arrows":{"to":{"enabled":true,"scaleFactor":0.55}},"color":{"color":"#526789","highlight":"#9d8cff"},"smooth":{"type":"dynamic"},"width":1.4},
     "physics":{"enabled":true,"solver":"forceAtlas2Based","forceAtlas2Based":{"gravitationalConstant":-45,"centralGravity":0.008,"springLength":145,"springConstant":0.08},"stabilization":{"iterations":120}},
     "interaction":{"hover":true,"navigationButtons":true,"keyboard":{"enabled":true},"multiselect":false,"tooltipDelay":120,"zoomView":true,"dragView":true}}
    """)

    for path, data in normalized.items():
        symbols = data.get("symbols", [])
        functions = sum(1 for s in symbols if "function" in str(s.get("kind", "")))
        classes = sum(1 for s in symbols if s.get("kind") == "class")
        package = _package(path)
        layer = _layer(path)
        tooltip = (f"{html_lib.escape(path)}<br>Functions: {functions}<br>Classes: {classes}<br>"
                   f"Imports: {len(data.get('imports', []))}<br>Package: {html_lib.escape(package)}<br>"
                   f"Layer: {html_lib.escape(layer)}")
        attrs = _json_safe({
            "label": html_lib.escape(PurePosixPath(path).name), "title": tooltip,
            "group": package, "package": package, "layer": layer, "module": path,
            "symbols": symbols, "imports": data.get("imports", []),
            "shape": "dot", "size": min(30, 13 + functions + classes * 2),
            "color": {"background":"#7167f8","border":"#b5afff",
                      "highlight":{"background":"#a49cff","border":"#ffffff"}},
        })
        net.add_node(_json_safe(path), **attrs)
    for source, target in sorted(links):
        net.add_edge(_json_safe(source), _json_safe(target))

    generated = net.generate_html()
    controls = _controls(packages, layers)
    generated = generated.replace('<body>', '<body>' + controls, 1)
    generated = generated.replace('</body>', _INTERACTION_SCRIPT + '</body>', 1)
    return generated, {"nodes": len(normalized), "edges": len(links)}
