#!/usr/bin/env bash
# ============================================================================
# Откат дизайна админки к снимку, сделанному до перехода на Ethereal Glass.
#
#   bash scripts/design-rollback.sh            # показать, что изменится
#   bash scripts/design-rollback.sh --apply    # выполнить откат
#
# Восстанавливает ВСЁ дерево admin_frontend/ из тега design/legacy-tactical-
# telemetry: и изменённые файлы, и удалённые, и — что важно — удаляет файлы,
# добавленные после снимка. `git checkout <tag> -- <path>` сам по себе
# последнего не делает: новые компоненты просто остались бы лежать и
# продолжали импортироваться, дав сломанную полусмесь двух дизайнов.
#
# Скрипт не коммитит и не деплоит: после него нужно проверить `git diff`,
# закоммитить и отдельно запустить деплой.
# ============================================================================
set -euo pipefail

TAG="design/legacy-tactical-telemetry"
SCOPE="admin_frontend"

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

say()  { printf '%s\n' "$*"; }
fail() { printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }

git rev-parse --git-dir >/dev/null 2>&1 || fail "не git-репозиторий: $REPO_ROOT"
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null \
  || fail "тег $TAG не найден. Достаньте его: git fetch origin --tags"

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

# Файлы, существующие сейчас, но отсутствовавшие в снимке — их надо удалить,
# иначе останутся «сироты» из нового дизайна.
mapfile -t ORPHANS < <(
  comm -13 \
    <(git ls-tree -r --name-only "$TAG" -- "$SCOPE" | sort) \
    <(git ls-files -- "$SCOPE" | sort)
)

say "Откат дизайна админки"
say "  репозиторий : $REPO_ROOT"
say "  ветка       : $(git rev-parse --abbrev-ref HEAD)"
say "  снимок      : $TAG ($(git rev-parse --short "$TAG^{commit}"))"
say ""

CHANGED="$(git diff --name-only "$TAG" -- "$SCOPE" || true)"

if [[ -z "$CHANGED" && ${#ORPHANS[@]} -eq 0 ]]; then
  say "Расхождений с снимком нет — откатывать нечего."
  exit 0
fi

if [[ -n "$CHANGED" ]]; then
  say "Будут восстановлены из снимка ($(printf '%s\n' "$CHANGED" | wc -l | tr -d ' ') шт.):"
  printf '%s\n' "$CHANGED" | sed 's/^/  ~ /'
  say ""
fi

if [[ ${#ORPHANS[@]} -gt 0 ]]; then
  say "Будут УДАЛЕНЫ (появились после снимка, ${#ORPHANS[@]} шт.):"
  printf '  - %s\n' "${ORPHANS[@]}"
  say ""
fi

if [[ $APPLY -eq 0 ]]; then
  say "Это предпросмотр. Чтобы выполнить:  bash scripts/design-rollback.sh --apply"
  exit 0
fi

if ! git diff --quiet -- "$SCOPE" || ! git diff --cached --quiet -- "$SCOPE"; then
  say "ВНИМАНИЕ: в $SCOPE есть незакоммиченные изменения — они будут потеряны."
  read -r -p "Продолжить? [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || fail "отменено"
fi

git checkout "$TAG" -- "$SCOPE"
if [[ ${#ORPHANS[@]} -gt 0 ]]; then
  git rm -q -f --ignore-unmatch -- "${ORPHANS[@]}"
fi

say ""
say "Готово. Дизайн возвращён к снимку $TAG."
say ""
say "Дальше вручную:"
say "  1. cd admin_frontend && npm install      # package.json тоже откатился"
say "  2. npm run build                         # проверить, что собирается"
say "  3. git commit -am 'откат дизайна к $TAG'"
say "  4. bash /c/deploy/deploy.sh              # отдельным решением"
