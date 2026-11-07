"""Apply Sento display names through Komga's API; never touch media or progress."""

import argparse
import base64
import json
import os
from pathlib import Path, PurePosixPath
import re
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


SERIES_FOLDER = re.compile(r"(.+) \[mangabaka-\d+\]")
LANGUAGE = re.compile(r" \[[a-z]{2,3}(?:-[A-Za-z]+)?\]")
NUMBER = re.compile(r"\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?")


def relative_parts(path, root):
    """Reject sibling roots, traversal, and staging/review/trash folders."""
    path = PurePosixPath(path)
    if ".." in path.parts:
        return ()
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return ()
    if any(p.startswith(".") or p == "review" for p in parts):
        return ()
    return parts


def series_title(series, library):
    parts = relative_parts(series["url"], library["root"])
    if len(parts) != 2 or not (match := SERIES_FOLDER.fullmatch(parts[0])):
        return None
    title = match[1] + " · " + LANGUAGE.sub("", parts[1])
    title = title.replace(" · Standard Edition", "")
    if library["name"] == "Chapters":
        title = title.replace(" · Chapters", "")
    return title


def book_title(book, series, library):
    parts = relative_parts(book["url"], series["url"])
    if len(parts) != 1:
        return None
    # ComicInfo's Number is authoritative, including decimals and collected ranges.
    number = book["metadata"].get("number", "").strip()
    if not NUMBER.fullmatch(number):
        return None
    number = "-".join(str(int(n.split(".")[0])) + ("." + n.split(".")[1] if "." in n else "") for n in number.split("-"))
    prefix = "Ch." if library["name"] == "Chapters" else "Vol."
    return prefix + " " + number


def plan(libraries, series_list, books):
    """Return title-only patches; unrelated libraries and removed entries are ignored."""
    libraries = {lib["id"]: lib for lib in libraries if lib["name"] in {"Volumes", "Chapters"}}
    selected = {}
    patches = []
    for series in series_list:
        library = libraries.get(series["libraryId"])
        if series.get("deleted") or not library:
            continue
        title = series_title(series, library)
        if not title:
            continue
        selected[series["id"]] = (series, library)
        desired = {"title": title, "titleLock": True, "titleSort": title, "titleSortLock": True}
        if any(series["metadata"].get(k) != v for k, v in desired.items()):
            patches.append(("/api/v1/series/" + quote(series["id"], safe="") + "/metadata", desired))
    for book in books:
        if book.get("deleted") or book["seriesId"] not in selected:
            continue
        series, library = selected[book["seriesId"]]
        title = book_title(book, series, library)
        if not title:
            continue
        desired = {"title": title, "titleLock": True}
        if any(book["metadata"].get(k) != v for k, v in desired.items()):
            patches.append(("/api/v1/books/" + quote(book["id"], safe="") + "/metadata", desired))
    return patches


class Komga:
    def __init__(self):
        self.base = os.environ.get("KOMGA_BASE_URI", "http://komga.media.svc.cluster.local:8080").rstrip("/")
        if key_file := os.environ.get("KOMGA_API_KEY_FILE"):
            self.headers = {"X-API-Key": Path(key_file).read_text().strip()}
        else:
            credentials = os.environ["KOMF_KOMGA_USER"] + ":" + os.environ["KOMF_KOMGA_PASSWORD"]
            self.headers = {"Authorization": "Basic " + base64.b64encode(credentials.encode()).decode()}

    def request(self, path, data=None):
        headers = self.headers | {"Accept": "application/json"}
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode()
        request = Request(self.base + path, headers=headers, data=body, method="PATCH" if body else "GET")
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None

    def pages(self, path):
        items = []
        page = 0
        while True:
            result = self.request(path + "?" + urlencode({"size": 200, "page": page}))
            items.extend(result["content"])
            if result["last"]:
                return items
            page += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: preview)")
    args = parser.parse_args()
    komga = Komga()
    # Fetch every page before changing titles: changing sort keys while paging skips entries.
    changes = plan(komga.request("/api/v1/libraries"), komga.pages("/api/v1/series"), komga.pages("/api/v1/books"))
    if args.apply:
        for path, patch in changes:
            komga.request(path, patch)
    else:
        for path, patch in changes:
            print(path, json.dumps(patch, ensure_ascii=False))
    print(f"{'Applied' if args.apply else 'Planned'} {len(changes)} title updates.")


if __name__ == "__main__":
    main()
