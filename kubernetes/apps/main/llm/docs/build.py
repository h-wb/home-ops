"""Draws ../DESIGN.md, flows.md and wiring.md (static SVG, no runtime).

    python3 kubernetes/apps/main/llm/docs/build.py [page.html]   # img/*.svg, and the page if named
    python3 kubernetes/apps/main/llm/docs/build.py --check       # fail if img/*.svg are stale

The diagrams come from the documents' Mermaid blocks. img/*.svg are what the
documents show on GitHub; the page is published as the "Assistant Flow Map"
artifact, so republish it there after changing any of the three documents.
"""
from html import escape
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
DESIGN = (HERE.parent / "DESIGN.md").read_text()
FLOWS_MD = (HERE / "flows.md").read_text()
WIRING_MD = (HERE / "wiring.md").read_text()


# ── tiny markdown readers ────────────────────────────────────────────────────
def inline(s):
    s = escape(s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)


def sections(text, level="## "):
    out, name, buf = {}, None, []
    for line in text.split("\n"):
        if line.startswith(level):
            if name is not None:
                out[name] = "\n".join(buf)
            name, buf = line[len(level):].strip(), []
        elif name is not None:
            buf.append(line)
    if name is not None:
        out[name] = "\n".join(buf)
    return out


def tables(body):
    found, rows = [], []
    for line in body.split("\n") + [""]:
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):
                rows.append(cells)
        elif rows:
            found.append(rows)
            rows = []
    return found


def items(body, ordered=False):
    mark = re.compile(r"^\d+\. " if ordered else r"^- ")
    out = []
    for line in body.split("\n"):
        if mark.match(line):
            out.append(mark.sub("", line))
        elif out and line.startswith("  ") and line.strip():
            out[-1] += " " + line.strip()
        elif out and not line.strip():
            continue
        elif out and not line.startswith(" "):
            break
    return out


def paragraphs(body):
    out, buf, fenced = [], [], False
    for line in body.split("\n"):
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced or line.startswith(("|", "- ", "#", "<", "![")) or re.match(r"^\d+\. ", line) or line.startswith("  "):
            if buf:
                out.append(" ".join(buf))
                buf = []
            continue
        if line.strip():
            buf.append(line.strip())
        elif buf:
            out.append(" ".join(buf))
            buf = []
    if buf:
        out.append(" ".join(buf))
    return out


def mermaid(body):
    m = re.search(r"```mermaid\n(.*?)```", body, flags=re.S)
    return m.group(1).split("\n") if m else []


def html_table(rows, cls=""):
    head = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
    body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
    return f'<div class="tablewrap"><table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


# ── drawing helpers ──────────────────────────────────────────────────────────
def t(x, y, s, cls="d-text", anchor="middle"):
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="{cls}">{escape(s)}</text>'


def badge(x, y, n):
    return (f'<circle cx="{x}" cy="{y}" r="10" class="badge"/>'
            f'<text x="{x}" y="{y + 3.6}" text-anchor="middle" class="badge-t">{n}</text>')


def diamond(x, y, r, cls):
    return f'<polygon points="{x},{y - r} {x + r},{y} {x},{y + r} {x - r},{y}" class="{cls}"/>'


# ── flows: Mermaid sequence → lane drawing ───────────────────────────────────
W = 968
SCOPE_X = 606
LANES = {
    "Y": dict(x=70, sub="phone, laptop", cls="you"),
    "H": dict(x=220, sub="trusted models", cls="private"),
    "T": dict(x=370, sub="named tools", cls="private"),
    "P": dict(x=520, sub="trusted models", cls="private"),
    "G": dict(x=704, sub="any model", cls="general"),
    "X": dict(x=886, sub="monitoring, git host", cls="general"),
}
HEAD_Y, HEAD_H, HEAD_W = 40, 46, 132
FIRST_Y = 122
WRITES_TO = {"T", "P", "G"}


def parse_sequence(lines):
    names, steps = {}, []
    for raw in lines:
        line = raw.strip()
        if m := re.match(r"participant (\w+) as (.+)$", line):
            names[m[1]] = m[2]
        elif m := re.match(r"(\w+)(-->>|->>)(\w+): (.+)$", line):
            steps.append(dict(kind="msg", frm=m[1], to=m[3], label=m[4], planned=m[2] == "-->>"))
        elif m := re.match(r"Note over (\w+): (.+)$", line):
            steps.append(dict(kind="note", at=m[1], lines=m[2].split("<br/>"), planned=True))
    return names, steps


def sequence(names, steps, label):
    used = set()
    for s in steps:
        used |= {s["at"]} if s["kind"] == "note" else {s["frm"], s["to"]}
    body, y = [], FIRST_Y
    for n, s in enumerate(steps, 1):
        planned = " planned" if s.get("planned") else ""
        if s["kind"] == "note":
            lane, lines = LANES[s["at"]], s["lines"]
            h = 30 if len(lines) == 1 else 44
            w = 132 if s["at"] == "Y" else 150
            body.append(f'<rect x="{lane["x"] - w / 2}" y="{y}" width="{w}" height="{h}" rx="4" '
                        f'class="note note-{lane["cls"]}{planned}"/>')
            for i, line in enumerate(lines):
                body.append(t(lane["x"] + 6, y + (19 if len(lines) == 1 else 18 + i * 15), line, "d-text d-small"))
            body.append(badge(lane["x"] - w / 2, y + h / 2, n))
            y += h + 18
            continue
        x1, x2 = LANES[s["frm"]]["x"], LANES[s["to"]]["x"]
        crosses = min(x1, x2) < SCOPE_X < max(x1, x2)
        gate = crosses and x2 > x1 and s["frm"] != "Y"
        asks = s["frm"] == "H" and s["to"] in WRITES_TO and not gate
        g = " gate" if gate else ""
        ly, d = y + 20, (1 if x2 > x1 else -1)
        body.append(f'<line x1="{x1 + d * 10}" y1="{ly}" x2="{x2 - d * 8}" y2="{ly}" class="line{planned}{g}"/>')
        body.append(f'<polygon points="{x2},{ly} {x2 - d * 9},{ly - 4.5} {x2 - d * 9},{ly + 4.5}" class="head{g}"/>')
        body.append(t((x1 + x2) / 2 + d * 4, ly - 8, s["label"], "d-text" + (" d-gate" if gate else "")))
        if gate:
            body.append(diamond(SCOPE_X, ly, 8, "gate-mark"))
        elif asks:
            body.append(diamond(x2 - d * 26, ly, 7, "ask-mark"))
        body.append(badge(x1, ly, n))
        y += 44
    height = y + 22
    out = [f'<svg viewBox="0 0 {W} {height}" role="img" aria-label="{escape(label)}" class="seq">',
           f'<rect x="0" y="0" width="{W}" height="{height}" class="sheet"/>',
           t(370, 24, "PRIVATE SCOPE", "d-mono d-private"), t(795, 24, "GENERAL SCOPE", "d-mono d-general"),
           f'<line x1="{SCOPE_X}" y1="12" x2="{SCOPE_X}" y2="{height - 22}" class="scope"/>',
           t(SCOPE_X, height - 8, "scope line", "d-mono d-muted")]
    for key, lane in LANES.items():
        idle = "" if key in used else " idle"
        out.append(f'<line x1="{lane["x"]}" y1="{HEAD_Y + HEAD_H}" x2="{lane["x"]}" y2="{height - 22}" class="lifeline{idle}"/>')
        out.append(f'<g class="lane{idle}"><rect x="{lane["x"] - HEAD_W / 2}" y="{HEAD_Y}" width="{HEAD_W}" height="{HEAD_H}" '
                   f'rx="5" class="box box-{lane["cls"]}"/>' + t(lane["x"], HEAD_Y + 20, names.get(key, key), "d-text d-strong")
                   + t(lane["x"], HEAD_Y + 36, lane["sub"], "d-text d-small d-muted") + "</g>")
    return "".join(out + body) + "</svg>"


IMAGES = {}


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def flows_html():
    out = []
    for title, body in sections(FLOWS_MD).items():
        m = re.match(r"([A-Z])\. (.+)$", title)
        if not m:
            continue
        status = re.search(r"^Status: (.+)$", body, flags=re.M)[1]
        paras = [p for p in paragraphs(body) if not p.startswith("Status:")]
        notes = dict(i.split(": ", 1) for i in items(body))
        names, steps = parse_sequence(mermaid(body))
        cls = {"works today": "live", "partly today": "partly"}.get(status, "planned")
        drawing = IMAGES[f"flow-{m[1].lower()}"] = sequence(names, steps, m[2] + ": " + paras[0])
        out.append(f"""
<article class="flow" id="flow-{m[1].lower()}">
  <div class="flow-head"><span class="eyebrow">Flow {m[1]}</span><h3>{inline(m[2])}</h3><span class="status {cls}">{escape(status)}</span></div>
  <p>{inline(paras[0])}</p>
  <figure>
    <div class="scroll">{drawing}</div>
    <figcaption>{inline(paras[1]) if len(paras) > 1 else ''}</figcaption>
  </figure>
  <dl class="verdict">
    <div><dt>Why it is safe</dt><dd>{inline(notes.get('Why it is safe', ''))}</dd></div>
    <div><dt>What it costs</dt><dd>{inline(notes.get('What it costs', ''))}</dd></div>
  </dl>
</article>""")
    return "".join(out)


# ── wiring: Mermaid flowchart → bus drawing ──────────────────────────────────
AG_X, AG_W, BUS_X = 16, 172, 208
C1_X, C1_W, BUS2_X = 424, 200, 654
C2_X, C2_W = 722, 184
ROW, BOX_H = 62, 44


def parse_flowchart(lines):
    nodes, edges = {}, []
    for raw in lines:
        line = raw.strip()
        if m := re.match(r'(\w+)\["(.+?)"\](?::::(\w+))?$', line):
            nodes[m[1]] = dict(lines=m[2].split("<br/>"), cls=m[3] or "shared")
        elif m := re.match(r'(\w+) (-->|-\.->)(?:\|"(.+?)"\|)? ?(\w+)$', line):
            edges.append(dict(src=m[1], dst=m[4], label=m[3] or "", off=m[2] == "-.->"))
    return nodes, edges


def node_box(x, y, w, node):
    cls = {"outside": "you", "shared": "shared"}.get(node["cls"], node["cls"])
    out = [f'<rect x="{x}" y="{y - BOX_H / 2}" width="{w}" height="{BOX_H}" rx="5" class="box box-{cls}"/>']
    lines = node["lines"]
    if len(lines) == 1:
        out.append(t(x + w / 2, y + 4.5, lines[0], "d-text d-strong"))
    else:
        out.append(t(x + w / 2, y - 3, lines[0], "d-text d-strong"))
        out.append(t(x + w / 2, y + 13, lines[1], "d-text d-small d-muted"))
    return "".join(out)


def h_arrow(x1, x2, y, off):
    o = " off" if off else ""
    return (f'<line x1="{x1}" y1="{y}" x2="{x2 - 8}" y2="{y}" class="line{o}"/>'
            f'<polygon points="{x2},{y} {x2 - 9},{y - 4.5} {x2 - 9},{y + 4.5}" class="head{o}"/>')


def wiring_svg(nodes, edges, label):
    agent = next(iter(nodes))
    rows = []
    for e in (e for e in edges if e["src"] == agent):
        kids = [k for k in edges if k["src"] == e["dst"]]
        if kids:
            for i, k in enumerate(kids):
                rows.append(dict(c1=e["dst"] if i == 0 else None, c2=k["dst"], e1=e if i == 0 else None, e2=k, first=i == 0))
        elif nodes[e["dst"]]["cls"] == "outside":
            rows.append(dict(c1=None, c2=e["dst"], e1=e, e2=None, first=True))
        else:
            rows.append(dict(c1=e["dst"], c2=None, e1=e, e2=None, first=True))
    ys = [40 + i * ROW for i in range(len(rows))]
    height = ys[-1] + 40
    ay = (ys[0] + ys[-1]) / 2
    o = [f'<svg viewBox="0 0 920 {height}" role="img" aria-label="{escape(label)}" class="wire">',
         f'<rect x="0" y="0" width="920" height="{height}" class="sheet"/>']
    starts = [y for y, r in zip(ys, rows) if r["e1"]]
    o.append(f'<line x1="{AG_X + AG_W}" y1="{ay}" x2="{BUS_X}" y2="{ay}" class="line"/>')
    o.append(f'<line x1="{BUS_X}" y1="{min(starts + [ay])}" x2="{BUS_X}" y2="{max(starts + [ay])}" class="line"/>')
    parent_y = None
    for y, r in zip(ys, rows):
        if r["e1"]:
            target = C1_X if r["c1"] else C2_X
            o.append(h_arrow(BUS_X, target, y, r["e1"]["off"]))
            o.append(t(BUS_X + 12, y - 8, r["e1"]["label"], "d-text d-small" + (" d-gate" if r["e1"]["off"] else ""), "start"))
        if r["c1"]:
            o.append(node_box(C1_X, y, C1_W, nodes[r["c1"]]))
            parent_y = y
        if r["e2"]:
            if r["first"]:
                o.append(h_arrow(C1_X + C1_W, C2_X, y, r["e2"]["off"]))
            else:
                o.append(f'<line x1="{BUS2_X}" y1="{parent_y}" x2="{BUS2_X}" y2="{y}" class="line"/>')
                o.append(h_arrow(BUS2_X, C2_X, y, r["e2"]["off"]))
            if r["e2"]["label"]:
                o.append(t((C1_X + C1_W + C2_X) / 2, y - 8, r["e2"]["label"], "d-text d-small"))
        if r["c2"]:
            o.append(node_box(C2_X, y, C2_W, nodes[r["c2"]]))
    o.append(node_box(AG_X, ay, AG_W, nodes[agent]))
    return "".join(o) + "</svg>"


def wiring_html():
    secs = sections(WIRING_MD)
    out = [html_table(tables(secs["At a glance"])[0], "wide")]
    out += [f"<p>{inline(p)}</p>" for p in paragraphs(secs["At a glance"])]
    for title, body in secs.items():
        chart = mermaid(body)
        if not chart:
            continue
        nodes, edges = parse_flowchart(chart)
        drawing = IMAGES[f"wiring-{slug(title)}"] = wiring_svg(nodes, edges, title)
        notes = "".join(f"<li>{inline(i)}</li>" for i in items(body))
        out.append(f"""
<article class="flow">
  <div class="flow-head"><h3>{inline(title)}</h3></div>
  {''.join(f'<p>{inline(p)}</p>' for p in paragraphs(body))}
  <figure><div class="scroll">{drawing}</div></figure>
  {f'<ul class="notes">{notes}</ul>' if notes else ''}
</article>""")
    services = secs["Services that call models"]
    out.append(f'<article class="flow"><div class="flow-head"><h3>Services that call models</h3></div>'
               f'{"".join(f"<p>{inline(p)}</p>" for p in paragraphs(services))}{html_table(tables(services)[0])}</article>')
    differs = "".join(f"<li>{inline(i)}</li>" for i in items(secs["Differs from the design"], ordered=True))
    out.append(f'<article class="flow" id="differs"><div class="flow-head"><h3>Differs from the design</h3></div>'
               f'<ol class="differs">{differs}</ol></article>')
    return "".join(out)


# ── the map ──────────────────────────────────────────────────────────────────
def box(x, y, w, h, cls, lines, planned=False):
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" class="box box-{cls}{" planned" if planned else ""}"/>']
    for i, (text, style) in enumerate(lines):
        out.append(t(x + w / 2, y + 24 + i * 18, text, "d-text " + style))
    return "".join(out)


def arrow(points, cls=""):
    pts = " ".join(f"{x},{y}" for x, y in points)
    (x0, y0), (x1, y1) = points[-2], points[-1]
    dx, dy = (x1 > x0) - (x1 < x0), (y1 > y0) - (y1 < y0)
    tri = (f"{x1 + dx * 8},{y1} {x1 - dx},{y1 - 4.5} {x1 - dx},{y1 + 4.5}" if dx
           else f"{x1},{y1 + dy * 8} {x1 - 4.5},{y1 - dy} {x1 + 4.5},{y1 - dy}")
    return (f'<polyline points="{pts}" class="line {cls}"/>'
            f'<polygon points="{tri}" class="head {"gate" if "gate" in cls else ""}"/>')


def system_map():
    o = ['<svg viewBox="0 0 960 606" role="img" class="map" aria-label="Three places in two scopes: the assistant and the '
         'private workshop on the private side, the general workshop on the general side. Each uses its own side of the '
         'shared model, tool and memory services. Only the assistant starting a general agent crosses the scope line, '
         'after your approval.">', '<rect x="0" y="0" width="960" height="606" class="sheet"/>',
         t(374, 26, "PRIVATE SCOPE", "d-mono d-private"), t(374, 43, "trusted models only", "d-text d-small d-muted"),
         t(772, 26, "GENERAL SCOPE", "d-mono d-general"), t(772, 43, "any model", "d-text d-small d-muted"),
         '<rect x="176" y="136" width="396" height="224" rx="8" class="zone zone-private"/>',
         '<rect x="608" y="136" width="328" height="224" rx="8" class="zone zone-general"/>']
    for y, a, b in ((84, "You", "your devices"), (236, "Places", "one scope each"),
                    (418, "Models", "one gateway"), (477, "Tools", "one catalogue"), (536, "Memory", "a store per scope")):
        o += [t(24, y, a, "d-text d-strong", "start"), t(24, y + 16, b, "d-text d-small d-muted", "start")]
    o.append(box(192, 62, 140, 44, "you", [("Messaging app", "d-strong")]))
    o.append(box(432, 62, 484, 44, "you", [("Workshop app · one app, two hosts", "d-strong")]))
    o.append(box(192, 176, 140, 116, "private", [("Assistant", "d-strong"), ("talks, remembers,", "d-small"),
                                                 ("runs routines", "d-small"), ("no shell", "d-small d-muted")]))
    o.append(box(432, 176, 124, 116, "private", [("Private workshop", "d-strong"), ("agents with a shell", "d-small"),
                                                 ("private repos", "d-small d-muted"), ("yours, directly", "d-small d-muted")]))
    o.append(box(667, 176, 210, 116, "general", [("General workshop", "d-strong"), ("agents with a shell", "d-small"),
                                                 ("code repos", "d-small d-muted"), ("no private data", "d-small d-muted")]))
    o += [arrow([(262, 106), (262, 168)]), t(270, 128, "talk", "d-text d-small", "start"),
          arrow([(494, 106), (494, 168)]), t(502, 128, "watch, steer", "d-text d-small", "start"),
          arrow([(772, 106), (772, 168)]), t(780, 128, "watch, steer", "d-text d-small", "start"),
          arrow([(432, 234), (340, 234)]), t(386, 252, "chat bridge,", "d-text d-small d-muted"),
          t(386, 266, "today only", "d-text d-small d-muted"),
          arrow([(262, 292), (262, 330), (772, 330), (772, 300)], "planned gate"), diamond(590, 330, 9, "gate-mark"),
          t(420, 348, "starts agents", "d-text d-small d-gate"),
          t(690, 348, "after you approve the prompt", "d-text d-small d-gate"),
          arrow([(374, 360), (374, 388)]), t(384, 379, "reads freely, asks before a write", "d-text d-small", "start"),
          arrow([(772, 360), (772, 388)]), t(782, 379, "its own key, gateway, store", "d-text d-small", "start")]
    rows = ((396, "the models you trust with private data", "any model"),
            (455, "every tool: notes, tasks, location, home, cluster, jobs", "cluster, git host, homelab tasks, media"),
            (514, "private store", "general store"))
    for y, private, general in rows:
        o += [f'<rect x="176" y="{y}" width="396" height="48" rx="5" class="box box-private"/>',
              t(374, y + 29, private, "d-text d-small"),
              f'<rect x="608" y="{y}" width="328" height="48" rx="5" class="box box-general"/>',
              t(772, y + 29, general, "d-text d-small")]
    o += ['<line x1="590" y1="118" x2="590" y2="572" class="scope"/>',
          t(590, 592, "scope line · private data never moves to the right of it", "d-mono d-muted")]
    return "".join(o) + "</svg>"


# ── page ─────────────────────────────────────────────────────────────────────
CSS = """
/* Layout: one reading column; every drawing sits on its own "sheet" and uses the same
   left-to-right order (you, private, scope line, general), so patterns repeat. */
:root {
  --bg: #eef1f4; --surface: #fbfcfd; --ink: #17212b; --muted: #5a6876; --rule: #c5ced7;
  --private: #9a5200; --private-bg: #fbe9cf; --private-wash: #f8f0e2;
  --general: #1c58b0; --general-bg: #dde9fa; --general-wash: #eaf1fb;
  --gate: #c0271d;
  --sans: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --display: "IBM Plex Sans Condensed", "Arial Narrow", "IBM Plex Sans", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0f141a; --surface: #161d25; --ink: #e4e9ee; --muted: #93a0ad; --rule: #34404c;
  --private: #f0aa52; --private-bg: #3a2a10; --private-wash: #231b10;
  --general: #78aefc; --general-bg: #14294a; --general-wash: #121c2c;
  --gate: #ff7468; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #0f141a; --surface: #161d25; --ink: #e4e9ee; --muted: #93a0ad; --rule: #34404c;
  --private: #f0aa52; --private-bg: #3a2a10; --private-wash: #231b10;
  --general: #78aefc; --general-bg: #14294a; --general-wash: #121c2c;
  --gate: #ff7468; color-scheme: dark }

body { background: var(--bg); color: var(--ink); font-family: var(--sans); font-size: 16px; line-height: 1.55 }
.page { max-width: 1000px; margin: 0 auto; padding-block: 40px 72px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: flex; flex-direction: column; gap: 40px }
.view { display: flex; flex-direction: column; gap: 56px }
h1, h2, h3 { font-family: var(--display); font-weight: 600; line-height: 1.15; margin: 0; text-wrap: balance }
h1 { font-size: 2.5rem; letter-spacing: -0.01em }
h2 { font-size: 1.6rem }
h3 { font-size: 1.3rem }
p { margin: 0; max-width: 65ch }
code { font-family: var(--mono); font-size: .88em }
a { color: inherit }
.eyebrow { font-family: var(--mono); font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; color: var(--muted) }
.masthead { display: flex; flex-direction: column; gap: 14px }
.invariant { font-family: var(--display); font-size: 1.45rem; font-weight: 600; max-width: 32ch;
  border-left: 3px solid var(--gate); padding-left: 14px }
.tabs { display: flex; flex-wrap: wrap; gap: 8px; border-bottom: 1px solid var(--rule) }
.tabs a { font-family: var(--display); font-weight: 600; font-size: 1.1rem; text-decoration: none; color: var(--muted);
  padding: 8px 14px; border-bottom: 3px solid transparent; margin-bottom: -1px }
.tabs a[aria-current="page"] { color: var(--ink); border-bottom-color: var(--ink) }
.tabs a:focus-visible { outline: 2px solid var(--general); outline-offset: 2px }
.section { display: flex; flex-direction: column; gap: 18px }
.section > .intro { color: var(--muted) }

.legend { display: flex; flex-wrap: wrap; gap: 10px 22px; padding: 0; margin: 0; list-style: none;
  font-size: .86rem; color: var(--muted) }
.legend li { display: flex; align-items: center; gap: 8px }
.sw { width: 14px; height: 14px; border-radius: 3px; border: 1.5px solid }
.sw.private { background: var(--private-bg); border-color: var(--private) }
.sw.general { background: var(--general-bg); border-color: var(--general) }
.legend svg { width: 34px; height: 14px; flex: none }

figure { margin: 0; display: flex; flex-direction: column; gap: 10px }
.scroll { overflow-x: auto; border: 1px solid var(--rule); border-radius: 6px; background: var(--surface) }
svg.seq { display: block; width: 100%; min-width: 780px; height: auto }
svg.map { display: block; width: 100%; min-width: 800px; height: auto }
svg.wire { display: block; width: 100%; min-width: 760px; height: auto }
figcaption { font-size: .9rem; color: var(--muted); max-width: 70ch }

.sheet { fill: var(--surface) }
.d-text { fill: var(--ink); font-family: var(--sans); font-size: 12.5px }
.d-small { font-size: 11.5px }
.d-strong { font-weight: 600; font-size: 13px }
.d-muted { fill: var(--muted) }
.d-mono { font-family: var(--mono); font-size: 10.5px; letter-spacing: .12em }
.d-mono.d-muted { fill: var(--muted) }
.d-private { fill: var(--private) }
.d-general { fill: var(--general) }
.d-gate { fill: var(--gate); font-weight: 600 }
.box { stroke-width: 1.4 }
.box-private { fill: var(--private-bg); stroke: var(--private) }
.box-general { fill: var(--general-bg); stroke: var(--general) }
.box-you { fill: var(--surface); stroke: var(--ink) }
.box-shared { fill: var(--bg); stroke: var(--muted) }
.box.planned, .note.planned { stroke-dasharray: 6 4 }
.zone { stroke: none }
.zone-private { fill: var(--private-wash) }
.zone-general { fill: var(--general-wash) }
.note { stroke-width: 1.2 }
.note-private { fill: var(--private-bg); stroke: var(--private) }
.note-general { fill: var(--general-bg); stroke: var(--general) }
.note-you { fill: var(--surface); stroke: var(--ink) }
.line { stroke: var(--ink); stroke-width: 1.5; fill: none }
.line.planned { stroke-dasharray: 6 4 }
.line.gate { stroke: var(--gate); stroke-width: 2 }
.line.off { stroke: var(--gate); stroke-width: 2; stroke-dasharray: 2 5; stroke-linecap: round }
.head { fill: var(--ink) }
.head.gate, .head.off { fill: var(--gate) }
.gate-mark { fill: var(--gate); stroke: var(--surface); stroke-width: 2 }
.ask-mark { fill: var(--surface); stroke: var(--ink); stroke-width: 1.6 }
.lifeline { stroke: var(--rule); stroke-width: 1.2; stroke-dasharray: 2 5 }
.lifeline.idle { opacity: .5 }
.lane.idle { opacity: .38 }
.scope { stroke: var(--ink); stroke-width: 1.6; stroke-dasharray: 1 6; stroke-linecap: round }
.badge { fill: var(--ink) }
.badge-t { fill: var(--surface); font-family: var(--mono); font-size: 10.5px; font-weight: 600 }

.flows { display: flex; flex-direction: column; gap: 44px }
.flow { display: flex; flex-direction: column; gap: 14px; padding-top: 22px; border-top: 1px solid var(--rule) }
.flow-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 14px }
.status { font-family: var(--mono); font-size: .7rem; letter-spacing: .1em; text-transform: uppercase;
  padding: 3px 9px; border-radius: 99px; border: 1.5px solid var(--ink); white-space: nowrap; align-self: center }
.status.planned { border-style: dashed; color: var(--muted); border-color: var(--muted) }
.status.partly { border-style: dashed }
.status.live { background: var(--ink); color: var(--bg) }
.verdict { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px 28px; margin: 0 }
.verdict div { min-width: 0 }
.verdict dt { font-family: var(--mono); font-size: .7rem; letter-spacing: .12em; text-transform: uppercase; color: var(--muted) }
.verdict dd { margin: 4px 0 0; font-size: .95rem }

.rules { margin: 0; padding: 0; list-style: none; display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px 32px }
.rules li { min-width: 0; padding-top: 12px; border-top: 2px solid var(--ink) }
.rules strong { display: block; font-family: var(--display); font-size: 1.12rem; font-weight: 600; margin-bottom: 4px }
.rules span { color: var(--muted); font-size: .95rem }

.tablewrap { overflow-x: auto }
table { border-collapse: collapse; width: 100%; min-width: 520px; font-size: .93rem }
table.wide { min-width: 860px }
th, td { text-align: left; vertical-align: top; padding: 10px 14px 10px 0; border-bottom: 1px solid var(--rule) }
th { font-family: var(--mono); font-size: .7rem; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); font-weight: 500 }
td:first-child { font-weight: 600 }
td.p { color: var(--private); font-weight: 500 }
td.g { color: var(--general); font-weight: 500 }

.plain, .notes, .differs { margin: 0; padding-left: 1.2em; display: flex; flex-direction: column; gap: 8px; font-size: .95rem; max-width: 72ch }
.differs li::marker { font-family: var(--mono); color: var(--gate); font-weight: 600 }
.cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 28px 44px }
.cols > div { min-width: 0; display: flex; flex-direction: column; gap: 10px }
footer { color: var(--muted); font-size: .85rem; border-top: 1px solid var(--rule); padding-top: 16px }
"""

LINE = '<svg viewBox="0 0 34 14" aria-hidden="true"><line x1="1" y1="7" x2="33" y2="7" class="line{}"/>{}</svg>'
LEGEND_FLOWS = f"""
<ul class="legend">
  <li><span class="sw private"></span>private scope</li>
  <li><span class="sw general"></span>general scope</li>
  <li>{LINE.format('', '')}works today</li>
  <li>{LINE.format(' planned', '')}planned</li>
  <li>{LINE.format('', diamond(17, 7, 6, 'ask-mark'))}changes something, asks you first</li>
  <li>{LINE.format(' gate', diamond(17, 7, 6, 'gate-mark'))}crosses to general, after your approval</li>
</ul>"""
LEGEND_WIRING = f"""
<ul class="legend">
  <li><span class="sw private"></span>private scope</li>
  <li><span class="sw general"></span>general scope</li>
  <li>{LINE.format('', '')}as designed</li>
  <li>{LINE.format(' off', '')}differs from the design</li>
</ul>"""

design = sections(DESIGN)
# Which revision of the documents the page shows, so a stale page can be told apart.
STAMP = subprocess.run(["git", "log", "-1", "--format=commit %h, %cs", "--", "."], cwd=HERE.parent,
                       capture_output=True, text=True).stdout.strip() or "an unknown revision"
rule = re.search(r"^\*\*(.+)\*\*$", design["The rule"], flags=re.M)[1]
trusted = tables(design["The rule"])[0]
roles = tables(design["Roles"])[0]
to_decide = items(design["Open"].split("To verify:")[0])
roadmap = items(design["Getting there"], ordered=True)
differs_count = len(items(sections(WIRING_MD)["Differs from the design"], ordered=True))

PAGE = f"""<title>Assistant Flow Map</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>{CSS}</style>
<div class="page">

<header class="masthead">
  <span class="eyebrow">home-ops · assistant and agents</span>
  <h1>Assistant Flow Map</h1>
  <p class="invariant">{inline(rule)}</p>
  <nav class="tabs" aria-label="Pages">
    <a href="#flows" data-tab="flows">Flows, by design</a>
    <a href="#wiring" data-tab="wiring">Wiring, today</a>
  </nav>
</header>

<main class="view" data-view="flows">
<section class="section">
  <p>One assistant, two workshops and three shared services. Every flow is drawn in the same order,
  private on the left and general on the right, so you can judge each one by what crosses the line in the middle.</p>
  <p>The page is written in roles. Which model is trusted, and which product fills a role, is a setting.
  Today's choices are listed once, <a href="#cast">at the end</a>.</p>
  {LEGEND_FLOWS}
</section>

<section class="section" id="map">
  <h2>The map</h2>
  <p class="intro">What exists, where it sits, and what it can reach.</p>
  <figure>
    <div class="scroll">{IMAGES.setdefault("map", system_map())}</div>
    <figcaption>Three places in two scopes. Each place uses its own side of the shared services.
    One link crosses the scope line: the assistant starting an agent in the general workshop, and it waits for your approval.</figcaption>
  </figure>
</section>

<section class="section" id="patterns">
  <h2>Five patterns</h2>
  <p class="intro">Every flow follows from these. If a flow breaks one, the flow is wrong.</p>
  <ul class="rules">
    <li><strong>Trust is a list</strong><span>Private work runs on the models you trust with it, and general work on any model. Moving a model between the two lists changes no arrow on this page.</span></li>
    <li><strong>Left is free, right is gated</strong><span>Anything may move from general to private. From private to general, only a prompt you approved.</span></li>
    <li><strong>Reads are free, writes ask</strong><span>The assistant reaches everything through named tools. Reading never asks. A tool that changes something runs after you say yes.</span></li>
    <li><strong>One assistant, a workshop per scope</strong><span>The assistant talks, remembers and acts through tools, with no shell. A workshop is where agents with a shell work, and where you work directly.</span></li>
    <li><strong>Repos hold code, services hold data</strong><span>Any model can write the code because the data is never in the repo. The private side runs it on the real thing.</span></li>
  </ul>
</section>

<section class="section" id="flow-list">
  <h2>The flows</h2>
  <p class="intro">Read each one as a short story, top to bottom. An arrow shows where information moves, and its
  numbered dot marks where that information comes from. Greyed columns take no part in that flow.</p>
  <div class="flows">{flows_html()}</div>
</section>

<section class="section" id="doors">
  <h2>The three shared doors</h2>
  <p class="intro">Every agent reaches models, tools and memory the same way. Its scope decides what is behind each door.</p>
  <div class="tablewrap">
  <table>
    <thead><tr><th>Door</th><th>Private agents get</th><th>General agents get</th><th>What enforces it</th></tr></thead>
    <tbody>
      <tr><td>Models</td><td class="p">The models you trust with private data</td><td class="g">Any model</td><td>Each agent's key lists the models it may call</td></tr>
      <tr><td>Tools</td><td class="p">Every tool, including notes, personal tasks, location, health, home and jobs</td><td class="g">Cluster, git host, homelab tasks, media. None of the private ones</td><td>A network rule admits only that scope's agents to its gateway</td></tr>
      <tr><td>Memory</td><td class="p">The private store. Reading the general one is still to check</td><td class="g">The general store</td><td>Two separate stores with separate keys</td></tr>
    </tbody>
  </table>
  </div>
</section>

<section class="section" id="next">
  <h2>What is left</h2>
  <div class="cols">
    <div><span class="eyebrow">Still to decide</span><ul class="plain">{''.join(f'<li>{inline(i)}</li>' for i in to_decide)}</ul></div>
    <div><span class="eyebrow">Getting there, in order</span><ol class="plain">{''.join(f'<li>{inline(i)}</li>' for i in roadmap)}</ol></div>
  </div>
</section>

<section class="section" id="cast">
  <h2>Today's choices</h2>
  <p class="intro">For reference. Any row can change without redrawing a flow.</p>
  {html_table([["Models", "Today"]] + trusted[1:])}
  {html_table(roles)}
</section>
</main>

<main class="view" data-view="wiring">
<section class="section">
  <p>How each agent is connected today: the path its model calls take, where its tools come from, and where it
  remembers things. This page uses real names, because it describes what is deployed.</p>
  <p>A dotted red arrow differs from the design. There are {differs_count} such differences, <a href="#differs">listed at the end</a>.</p>
  {LEGEND_WIRING}
</section>
<section class="section">
  <h2>At a glance</h2>
  <div class="flows">{wiring_html()}</div>
</section>
</main>

<footer>Drawn from <code>DESIGN.md</code>, <code>docs/flows.md</code> and <code>docs/wiring.md</code> in
<code>kubernetes/apps/main/llm</code> of home-ops, as of {STAMP}. Those documents are the source;
if this page and they disagree, the page is the stale one.</footer>
</div>
<script>
(function () {{
  var views = document.querySelectorAll("[data-view]"), tabs = document.querySelectorAll("[data-tab]");
  function show() {{
    var hash = location.hash.slice(1);
    var view = hash === "wiring" || hash === "differs" ? "wiring" : "flows";
    views.forEach(function (v) {{ v.hidden = v.dataset.view !== view; }});
    tabs.forEach(function (a) {{
      if (a.dataset.tab === view) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    }});
    var target = hash && document.getElementById(hash);
    if (target) target.scrollIntoView();
  }}
  window.addEventListener("hashchange", show);
  show();
}})();
</script>
"""

# ── standalone drawings for the documents ────────────────────────────────────
LIGHT = re.search(r":root \{\n(.*?)\n\}", CSS, flags=re.S)[1]
DARK = re.search(r':root\[data-theme="dark"\] \{\n(.*?)color-scheme: dark \}', CSS, flags=re.S)[1]
SVG_CSS = CSS[CSS.index(".sheet {"):CSS.index(".flows {")]
# An image cannot load web fonts, so the files use the system ones.
FONTS = ('--sans: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; --display: var(--sans); '
         '--mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;')
STYLE = (f"<style>svg {{ {LIGHT} {FONTS} }} @media (prefers-color-scheme: dark) {{ svg {{ {DARK} }} }} {SVG_CSS}</style>")


def standalone(svg):
    return svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1).replace(">", ">" + STYLE, 1) + "\n"


files = {HERE / "img" / f"{name}.svg": standalone(svg) for name, svg in IMAGES.items()}
if "--check" in sys.argv:
    stale = [str(f.relative_to(HERE)) for f, text in files.items() if not f.exists() or f.read_text() != text]
    stale += [str(f.relative_to(HERE)) for f in (HERE / "img").glob("*.svg") if f not in files]
    if stale:
        sys.exit("stale drawings, run build.py: " + ", ".join(sorted(stale)))
    print(f"{len(files)} drawings are current")
else:
    (HERE / "img").mkdir(exist_ok=True)
    for f in (HERE / "img").glob("*.svg"):
        if f not in files:
            f.unlink()
    for f, text in files.items():
        f.write_text(text)
    print(f"wrote {len(files)} drawings to {HERE / 'img'}")
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(PAGE)
        print(sys.argv[1], len(PAGE))
