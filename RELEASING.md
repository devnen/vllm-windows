# Releasing a new patched wheel

End-to-end automated. **Two prerequisites** (one-time setup):

1. **`UPSTREAM_WHEEL_URL` repo variable** — set under
   *Settings → Secrets and variables → Actions → Variables → New repository variable*.
   Value: a direct download URL for the upstream `SystemPanic/vllm-windows`
   wheel you want to base the release on. Example:

   ```
   https://github.com/SystemPanic/vllm-windows/releases/download/v0.19.0/vllm-0.19.0+cu124-cp312-cp312-win_amd64.whl
   ```

2. The repo's default `GITHUB_TOKEN` already has `contents: write` via the
   `permissions:` block in `.github/workflows/release.yml`. Nothing to set.

## Release flow

### Option A — tag and push (recommended)

```powershell
git tag v0.19.0-devnen.2
git push origin v0.19.0-devnen.2
```

The `release.yml` workflow:

1. Downloads the upstream wheel from `UPSTREAM_WHEEL_URL`.
2. Runs `windows_patches/repackage_wheel.py --tag devnen.2`.
3. Computes `SHA256SUMS.txt`.
4. Creates a GitHub Release on the tag with the wheel + sums attached
   and notes from `dist/RELEASE_NOTES.md`.

### Option B — Actions UI

Go to *Actions → Release patched wheel → Run workflow*. Optional inputs:
override `upstream_wheel_url`, set `tag` (e.g. `devnen.3`) and
`release_tag` (e.g. `v0.19.0-devnen.3`).

## Updating the patches

If you change anything in `windows_patches/*.py` or `vllm/`, ALSO bump
the local-version tag (`devnen.1` → `devnen.2`) so end users get a
distinguishable version string. The next tag-and-push reuses the
workflow above.

## Skipping CI for a release

Sometimes you want to release a wheel built locally rather than in CI
(e.g. you need a fresh CUDA toolchain CI doesn't have). Build it with:

```powershell
python windows_patches\repackage_wheel.py `
    --in <path-to-upstream.whl> `
    --tag devnen.N `
    --out dist
```

Then `gh release create v0.19.0-devnen.N --notes-file dist\RELEASE_NOTES.md
dist\vllm-0.19.0+devnen.N-*.whl dist\SHA256SUMS.txt` (after you regenerate
SHA256SUMS.txt).
