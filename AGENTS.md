# Repository contribution rules

## Git identity

- Use the existing personal Git identity for every commit. The identity recorded when these rules were added is `Lethean-2005 <letheanseourn05@gmail.com>`; preserve the user's personal username and email.
- Never use Codex, OpenAI, an AI bot, or another bot as author or committer.
- Never add AI attribution or AI co-author trailers to commit messages.
- Never modify global Git configuration.
- Before each commit, verify the effective author and committer identities, including environment overrides, both match the user's personal Git identity. If unavailable or different, inform the user and do not commit or push.
- Use professional Conventional Commits messages.
- Push only with the user's existing GitHub authentication. Do not replace authentication.
- Contribution graph eligibility depends on GitHub's verified-email and branch rules; do not promise eligibility from local configuration alone.

## Authorization and branches

- Local branch names are `develop` and `production`. Preserve other existing branches.
- Do not commit or push until the user explicitly authorizes those operations. Creating branches does not authorize committing or pushing.
- Preserve all existing working-tree changes when managing branches.

## Files

- Do not delete files under `scripts`.
- Preserve saved data, the `instance` directory, and environment configuration.

## Architecture

- Follow the responsibilities and staged cleanup plan in `docs/architecture.md`.
- Preserve existing URLs, public interfaces, count definitions and notification behavior during refactoring.
- Routes call services; services call repositories; repositories use database connections and query files. Services and repositories must not import routes.
- Prefer small verified extractions over a wholesale folder rewrite.
