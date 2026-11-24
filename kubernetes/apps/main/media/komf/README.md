---
area: "[[Homelab]]"
categories:
  - "[[Resources]]"
reviewed: 2026-11-24
summary: How Komga's two Sento libraries are set up, and what Komf adds to them and leaves to Sento.
created: 2026-11-07T23:39
---

# Sento libraries in Komga

Komga imports ComicInfo from Sento's Volumes and Chapters libraries. These settings live in Komga, not in git (not checked). Configure
both libraries with hourly scans, scan on startup, and directory exclusions
`/review`, `/.sento-trash`, and `/.sento-stage` in addition to the default NAS
exclusions. Disable Append volume to series title. Library roots remain set
in Komga itself.

Komf listens to these two libraries (`metadataLibraryFilter` in `app/config/application.yml`) and enriches Komga through its API,
authenticating as a local service account (`KOMGA_USERNAME`/`KOMGA_PASSWORD`
in the `komga` BWS item) because OIDC-provisioned accounts cannot use Basic
auth. It does not write ComicInfo, choose display titles, or override Sento's
book numbers and edition counts. Existing provider and cover preferences
otherwise remain in use.
