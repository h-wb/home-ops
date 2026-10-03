# Reviewing a Renovate dependency upgrade

This is a Flux GitOps repository for home Kubernetes clusters. A Renovate pull request
bumps a container image, a Helm chart (HelmRelease / OCIRepository), a GitHub Action or a
tool version. The diff is usually one line, so the review is about what that upgrade does
to this repository, not about the line itself. An approval lets the pull request
auto-merge, so do the research before deciding.

## 1. Identify the upgrade

From the title, body and diff: what is upgraded, the old and new version, and whether it
is a wrapper around something else (an image re-packaging upstream software, a chart
wrapping an application, an action wrapping a CLI). For a wrapper, find the inner
component's version change too: the two have independent changelogs.

## 2. Read the changelogs at their source

Use `gh` and `curl`. Cover every version between old and new, not only the newest.

- The release notes linked or quoted in the pull request body.
- The upstream repository's GitHub Releases (`gh release list`, `gh release view`).
- `CHANGELOG`, `UPGRADING` or migration files in the upstream repository.
- For a wrapper, the wrapped component's releases as well.
- With no changelog at all, the commit messages between the two tags, looking for:
  breaking, deprecat, remov, renam, migrat, drop, require.

If nothing can be found, say so in the summary rather than guessing.

## 3. Check what it means here

Read the files in this repository that use the upgraded component: the HelmRelease
values, Kustomizations, ConfigMaps, environment variables, and anything that depends on
it. A breaking change in a feature this repository does not use is not a finding.

konflate renders the pull request's Flux manifests before and after and reports the
result on the pull request: one comment per cluster from `bot-dupond[bot]`
(`gh pr view <number> --comments`) and the `Konflate (main)` / `Konflate (edge)` check
runs on the head commit (`gh api repos/<owner>/<repo>/commits/<sha>/check-runs`). Use it
to judge blast radius: a bump that rewrites many resources, touches a StatefulSet's volume
claims or selectors, or changes RBAC deserves a closer read than one that only moves an
image tag.

## 4. Findings and severity

Severity decides whether the pull request is approved, so use it precisely:

- **blocking**: a breaking change, removal or required migration that affects something
  this repository configures or relies on; or a failed Konflate check (render failure, or
  an image that does not exist in its registry), since the pull request cannot deploy.
  Name the file here that is affected and what has to change.
- **important**: a deprecation of something this repository uses (fix it now rather than
  ride the deprecated behaviour), or a default that changes behaviour here.
- **nit**: a new feature worth adopting later, or a cleanup the upgrade makes possible.
  Nits do not withhold the approval.

Raise nothing for changes that do not touch this repository.

## 5. The summary

Start the summary with a verdict: **Safe to merge** or **Not safe to merge**, with the
package and its old and new version. Then name the sources you read (release notes,
changelog, compare view), so a reader can tell what the verdict rests on. If no source
could be found, say that instead of implying the upgrade was checked.
