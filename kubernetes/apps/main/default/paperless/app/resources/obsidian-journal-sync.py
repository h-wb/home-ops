#!/usr/bin/env python3
"""Mirror Paperless journal entries into the Obsidian vault.

One note per journal document, following the vault's own conventions
(Vault/CLAUDE.md, "Scanned/handwritten journal"):

    Notes/YYYY-MM-DD <topic>.md
    ---
    categories:
      - "[[Journal]]"
    loc:
      - "[[City]]"          # only when a matching place note exists
    created: YYYY-MM-DDT00:00
    modified: YYYY-MM-DDTHH:mm
    ---
    ![[paperless-<ID>.pdf]]

    ## Transcript

    <OCR text>

Run it by hand inside the paperless pod:

    kubectl -n default exec deploy/paperless -- \
        setpriv --reuid 1000 --regid 1000 --clear-groups \
        python3 /scripts/obsidian-journal-sync.py [--dry-run]

Notes are matched to documents by their ![[paperless-<ID>.pdf]] embed, so
renaming a note in Obsidian will not create a duplicate here.

Only the "## Transcript" section is ever rewritten, and it is always the last
section: anything written above it is left untouched. Frontmatter of an
existing note is never touched (Linter owns `modified`).

File mtimes are preserved, because Wander sorts by them and a bulk run would
otherwise push every journal day to the top.
"""

import os
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/usr/src/paperless/src")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "paperless.settings")

import django  # noqa: E402

django.setup()

from documents.models import Document, Tag  # noqa: E402

VAULT = Path("/vault")
NOTES = VAULT / "Notes"
REFERENCES = VAULT / "References"
JOURNAL_TAG = "Journal"
MARKER = "## Transcript"
EMBED_RE = re.compile(r"!\[\[paperless-(\d+)\.pdf\]\]")
# Paperless journal titles are "YYYY-MM-DD — topic"; the vault wants the date
# as a filename prefix and the topic as the name, so split them apart.
TITLE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+—\s+(.*)$")
ILLEGAL = re.compile(r'[\\/:*?"<>|#^\[\]]')


def place_names():
    """Basenames of References/ notes, longest first, for `loc` matching."""
    if not REFERENCES.is_dir():
        return []
    return sorted((p.stem for p in REFERENCES.glob("*.md")), key=len, reverse=True)


def guess_loc(title, places):
    for name in places:
        if re.search(r"\b%s\b" % re.escape(name), title, re.I):
            return name
    return None


def index_notes():
    """paperless id -> note path, from the embeds already in the vault."""
    found = {}
    for path in VAULT.rglob("*.md"):
        if ".obsidian" in path.parts or ".trash" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in EMBED_RE.finditer(text):
            found.setdefault(int(m.group(1)), path)
    return found


def build_note(doc, topic, loc, transcript):
    fm = ['---', 'categories:', '  - "[[Journal]]"']
    if loc:
        fm += ['loc:', '  - "[[%s]]"' % loc]
    fm.append("created: %sT00:00" % doc.created.isoformat())
    fm.append("modified: %s" % datetime.now().strftime("%Y-%m-%dT%H:%M"))
    fm.append("---")
    body = "![[paperless-%d.pdf]]" % doc.pk
    return "\n".join(fm) + "\n" + body + "\n\n" + MARKER + "\n\n" + transcript + "\n"


def set_transcript(text, transcript):
    """Replace the trailing Transcript section, preserving everything above."""
    idx = text.find("\n" + MARKER)
    head = text[:idx] if idx != -1 else text.rstrip("\n")
    return head.rstrip("\n") + "\n\n" + MARKER + "\n\n" + transcript + "\n"


def write_preserving_mtime(path, text, exists):
    st = path.stat() if exists else None
    path.write_text(text, encoding="utf-8")
    if st is not None:
        os.utime(path, (st.st_atime, st.st_mtime))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not NOTES.is_dir():
        sys.exit("vault not mounted or Notes/ missing at %s" % NOTES)

    tag = Tag.objects.filter(name=JOURNAL_TAG).first()
    if tag is None:
        sys.exit("no %r tag in paperless" % JOURNAL_TAG)

    notes = index_notes()
    places = place_names()
    created = updated = unchanged = skipped = 0

    for doc in Document.objects.filter(tags=tag).order_by("created"):
        transcript = (doc.content or "").strip()
        if not transcript:
            print("SKIP  #%d %s: no OCR content" % (doc.pk, doc.created))
            skipped += 1
            continue

        path = notes.get(doc.pk)
        if path is None:
            m = TITLE_RE.match(doc.title)
            topic = m.group(2) if m else doc.title
            name = ILLEGAL.sub("", "%s %s" % (doc.created.isoformat(), topic)).strip()
            path = NOTES / (name + ".md")
            if path.exists():
                print("SKIP  #%d: %s exists without a paperless embed" % (doc.pk, path.name))
                skipped += 1
                continue
            text = build_note(doc, topic, guess_loc(doc.title, places), transcript)
            if not args.dry_run:
                write_preserving_mtime(path, text, exists=False)
            print("NEW   #%d -> %s" % (doc.pk, path.name))
            created += 1
            continue

        old = path.read_text(encoding="utf-8")
        new = set_transcript(old, transcript)
        if new == old:
            unchanged += 1
            continue
        if not args.dry_run:
            write_preserving_mtime(path, new, exists=True)
        print("TRANS #%d -> %s (%d chars)" % (doc.pk, path.name, len(transcript)))
        updated += 1

    print()
    print("new %d | transcript written %d | unchanged %d | skipped %d%s"
          % (created, updated, unchanged, skipped, "  [DRY RUN]" if args.dry_run else ""))


if __name__ == "__main__":
    main()
