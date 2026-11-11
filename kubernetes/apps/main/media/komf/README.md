# Sento libraries in Komga

Komga imports ComicInfo from Sento's Volumes and Chapters libraries. Configure
both libraries with hourly scans, scan on startup, and directory exclusions
`/review`, `/.sento-trash`, and `/.sento-stage` in addition to the default NAS
exclusions. Disable **Append volume to series title**. Library roots remain set
in Komga itself.

Komf listens to these two libraries and enriches Komga through its API,
authenticating as a local service account (`KOMGA_USERNAME`/`KOMGA_PASSWORD`
in the `komga` BWS item) because OIDC-provisioned accounts cannot use Basic
auth. It does not write ComicInfo, choose display titles, or override Sento's
book numbers and edition counts. Existing provider and cover preferences
otherwise remain in use.
