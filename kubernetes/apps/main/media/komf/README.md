# Sento libraries in Komga

Komga imports ComicInfo from Sento's Volumes and Chapters libraries. Configure
both libraries with hourly scans, scan on startup, and directory exclusions
`/review`, `/.sento-trash`, and `/.sento-stage` in addition to the default NAS
exclusions. Disable **Append volume to series title**. Library roots remain set
in Komga itself; the naming task reads them at runtime.

Komf listens to these two libraries and enriches Komga through its API. It does
not write ComicInfo, choose display titles, or override Sento's book numbers and
edition counts. Existing provider and cover preferences otherwise remain in use.

The `komga-titles` CronJob runs every ten minutes using the existing Komf
credentials. It derives series names from `<title> [mangabaka-ID]/<edition>` and
book titles from ComicInfo's imported number. It removes language markers and
the default edition label, retaining other edition labels and `(Colored)`.
Chapters use `Ch. N`; volumes use `Vol. N`. Title fields are locked so metadata
refreshes preserve them. Books, files, numbering and reading progress are not
modified. Removed entries, review, trash, staging, and unrecognized folder
structures are ignored.

To preview changes locally, set `KOMGA_BASE_URI` and `KOMGA_API_KEY_FILE` (the
path to a local key file), then run `python3 app/scripts/komga_titles.py` from
this directory. Add `--apply` to update names. Never commit credentials.

Regression checks: `mise exec -- python3 -B -m unittest discover -s tests -p
test_komga_titles.py` from the repository root. The job's log reports how many
title updates it applied; a settled library should report zero.
