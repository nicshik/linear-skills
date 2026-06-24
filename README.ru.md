# Linear Skills

[English](README.md)

Навыки-для-агентов и небольшие Python-скрипты для прямой работы с Linear GraphQL API.

Скрипты — обычный Python поверх Linear GraphQL API, поэтому запускаются из любого агентного рантайма с Python — Codex, Claude Code, Cursor, Antigravity, Windsurf — или из обычного шелла. `SKILL.md` несёт кросс-рантайм метаданные навыка; `agents/openai.yaml` — адаптер под Codex/OpenAI.

Репозиторий полезен, когда стандартный Linear connector недоступен, работает только на чтение или не может выполнить узкое действие, но нужен проверяемый способ автоматизировать Linear через личный API-ключ пользователя.

Репозиторий намеренно универсальный. Проектные очереди, правила доставки, префиксы задач и решение о переводе в `Done` должны жить в отдельном проектном wrapper-навыке или проектной документации.

## Что входит

| Навык | Назначение |
| --- | --- |
| `linear-custom-view` | Читает Linear Custom View и возвращает задачи в ручном порядке Linear. |
| `linear-change-status` | Меняет статус Linear-задачи и проверяет итог. |
| `linear-comment-issue` | Добавляет один комментарий к Linear-задаче после чтения и проверки цели. |
| `linear-create-issue` | Создаёт одну Linear-задачу после проверки команды, статуса, проекта и меток. |
| `linear-delete-issue` | Мягко удаляет одну Linear-задачу после чтения и явных защитных проверок. |
| `linear-custom-view-setup` | Проверяет и при необходимости создаёт один Custom View для команды. |
| `linear-custom-view-update` | Обновляет один существующий Custom View после чтения и проверки метаданных. |
| `linear-label-setup` | Проверяет и при необходимости создаёт метки задач в команде. |
| `linear-list-issues` | Читает отфильтрованные списки задач для миграций, разметки и проверки метаданных. |
| `linear-read-issue` | Читает одну Linear-задачу, при необходимости с комментариями и связями, без изменений Linear. |
| `linear-relation-setup` | Проверяет и при необходимости создаёт связь между двумя Linear-задачами. |
| `linear-update-issue` | Обновляет одну существующую задачу после чтения и затем проверяет результат. |

## Структура

```text
linear-change-status/
  SKILL.md
  agents/openai.yaml
  scripts/change_status.py
linear-comment-issue/
  SKILL.md
  agents/openai.yaml
  scripts/comment_issue.py
linear-create-issue/
  SKILL.md
  agents/openai.yaml
  scripts/create_issue.py
linear-delete-issue/
  SKILL.md
  agents/openai.yaml
  scripts/delete_issue.py
linear-custom-view/
  SKILL.md
  agents/openai.yaml
  scripts/custom_view.py
linear-custom-view-setup/
  SKILL.md
  agents/openai.yaml
  scripts/custom_view_setup.py
linear-custom-view-update/
  SKILL.md
  agents/openai.yaml
  scripts/custom_view_update.py
linear-label-setup/
  SKILL.md
  agents/openai.yaml
  scripts/label_setup.py
linear-list-issues/
  SKILL.md
  agents/openai.yaml
  scripts/list_issues.py
linear-read-issue/
  SKILL.md
  agents/openai.yaml
  scripts/read_issue.py
linear-relation-setup/
  SKILL.md
  agents/openai.yaml
  scripts/relation_setup.py
linear-update-issue/
  SKILL.md
  agents/openai.yaml
  scripts/update_issue.py
linear_common/
  graphql.py
docs/
  codex-approvals.md
examples/
  default.rules.snippet
scripts/
  validate.sh
  secret_scan.sh
  release_check.sh
```

## Требования

- Python 3.10 или новее.
- Личный Linear API key с доступом к нужной рабочей области.
- `ripgrep` для локальной проверки секретов.
- Опционально: `certifi` для стабильной TLS-проверки на macOS Python.

Установить Python-зависимости:

```bash
python3 -m pip install -r requirements.txt
```

## Настройка API-ключа

Задать ключ в shell:

```bash
export LINEAR_API_KEY=<linear-api-key>
```

Или передать локальный env-файл:

```bash
python3 linear-custom-view/scripts/custom_view.py <view-url> --env-file /path/to/.env.local
```

Env-файл должен содержать:

```text
LINEAR_API_KEY=<linear-api-key>
```

Не коммитьте реальные API-ключи. `.env` и `.env.*` игнорируются репозиторием.

## Использование

Прочитать Custom View в ручном порядке:

```bash
python3 linear-custom-view/scripts/custom_view.py \
  "https://linear.app/example/view/my-view-123abc" \
  --env-file /path/to/.env.local \
  --limit 50
```

Вернуть первую actionable-задачу и объяснить фильтр view:

```bash
python3 linear-custom-view/scripts/custom_view.py \
  "https://linear.app/example/view/my-view-123abc" \
  --env-file /path/to/.env.local \
  --json --first --explain-filter
```

Изменить статус задачи:

```bash
python3 linear-change-status/scripts/change_status.py LIN-123 Done \
  --env-file /path/to/.env.local
```

Прочитать одну задачу без изменения Linear:

```bash
python3 linear-read-issue/scripts/read_issue.py LIN-123 \
  --env-file /path/to/.env.local \
  --include-comments --include-relations
```

Найти открытые задачи без меток:

```bash
python3 linear-list-issues/scripts/list_issues.py \
  --team LIN \
  --project "Example Project" \
  --open-only \
  --without-labels \
  --env-file /path/to/.env.local \
  --json
```

Создать одну задачу после проверки метаданных:

```bash
python3 linear-create-issue/scripts/create_issue.py \
  --team LIN \
  --project "Example Project" \
  --status Backlog \
  --label Idea \
  --optional-label Product \
  --assignee "Example User" \
  --parent LIN-100 \
  --title "Example idea" \
  --description-file /path/to/body.md \
  --env-file /path/to/.env.local
```

Добавить один комментарий после проверки целевой задачи:

```bash
python3 linear-comment-issue/scripts/comment_issue.py LIN-123 \
  --body-file /path/to/comment.md \
  --env-file /path/to/.env.local
```

Мягко удалить одну задачу после защитных проверок:

```bash
python3 linear-delete-issue/scripts/delete_issue.py LIN-123 \
  --expect-status Done \
  --forbid-label Idea \
  --require-no-children \
  --require-no-relations \
  --require-no-comments \
  --env-file /path/to/.env.local \
  --dry-run \
  --json
```

Для живого удаления повторите проверенную команду без `--dry-run` и добавьте `--confirm LIN-123`. Helper не поддерживает безвозвратное удаление.

### Диагностика целевой задачи

Для чтения, комментариев и удаления по возможности используйте стабильные ключи задач, например `LIN-123`. Если `linear-read-issue`, `linear-comment-issue` или `linear-delete-issue` дошёл до Linear, но не нашёл целевую Issue, JSON-вывод содержит `error_category=not_found`, `error_code=issue_not_found`, `lookup`, `input_kind` и безопасную подсказку `hint`.

`issue_not_found` означает неверную, недоступную или относящуюся к другой рабочей области цель. Не описывайте это как отсутствие `LINEAR_API_KEY`, если helper явно не вернул `error_category=missing_api_key`.

Проверить и при необходимости создать метку в команде:

```bash
python3 linear-label-setup/scripts/label_setup.py \
  --team LIN \
  --label "Example label" \
  --description "Issues for the example stream" \
  --env-file /path/to/.env.local \
  --dry-run
```

Обновить существующую задачу после чтения:

```bash
python3 linear-update-issue/scripts/update_issue.py LIN-123 \
  --add-label "Example label" \
  --assignee "Example User" \
  --priority high \
  --append-description-file /path/to/addition.md \
  --env-file /path/to/.env.local \
  --dry-run
```

Задать приоритет одной задачи после чтения:

```bash
python3 linear-update-issue/scripts/update_issue.py LIN-123 \
  --priority high \
  --env-file /path/to/.env.local \
  --dry-run \
  --json
```

Допустимые значения priority: `none`, `no-priority`, `no_priority`, `urgent`, `high`, `medium`, `normal`, `low` и числа `0..4`.

Задать ручное место одной задачи после чтения:

```bash
python3 linear-update-issue/scripts/update_issue.py LIN-123 \
  --sort-order -199000 \
  --env-file /path/to/.env.local \
  --dry-run \
  --json
```

Для перестановки Custom View подготовьте полный целевой список задач, назначьте каждой своё значение `sortOrder`, сначала прогоните все команды с `--dry-run`, затем повторите без `--dry-run` только после проверки payload. Это меняет общий ручной порядок Linear для рабочей области, поэтому проектный wrapper должен сам строить и проверять полный список identifiers.

Проверить и при необходимости создать Custom View:

```bash
python3 linear-custom-view-setup/scripts/custom_view_setup.py \
  --team LIN \
  --project "Example Project" \
  --name "Example open work" \
  --label "Example label" \
  --open-only \
  --env-file /path/to/.env.local \
  --dry-run
```

Обновить существующий Custom View после чтения:

```bash
python3 linear-custom-view-update/scripts/custom_view_update.py \
  "Example open work" \
  --team LIN \
  --label "Example label" \
  --status Backlog \
  --open-only \
  --env-file /path/to/.env.local \
  --dry-run
```

Проверить и при необходимости создать связь между задачами:

```bash
python3 linear-relation-setup/scripts/relation_setup.py LIN-123 LIN-100 \
  --type related \
  --env-file /path/to/.env.local \
  --dry-run
```

Проверить переход без изменения Linear:

```bash
python3 linear-change-status/scripts/change_status.py LIN-123 Done \
  --env-file /path/to/.env.local \
  --dry-run
```

Предпросмотр пачки переходов по одному:

```bash
python3 linear-change-status/scripts/change_status.py \
  --batch-file status_changes.tsv \
  --env-file /path/to/.env.local \
  --json
```

Используйте `--json`, если результат читает другой инструмент или агент.

## Проектные wrapper-навыки

Эти навыки являются низкоуровневыми Linear helpers:

- `linear-custom-view` читает очередь Custom View и сохраняет ручной порядок.
- `linear-change-status` выполняет узкий переход статуса и проверяет результат.
- `linear-comment-issue` создаёт один комментарий после чтения и проверки целевой задачи.
- `linear-read-issue` читает одну задачу и, если нужно, комментарии или связи без изменений Linear.
- `linear-create-issue` создаёт одну задачу после проверки нужных метаданных и затем проверяет созданную задачу.
- `linear-delete-issue` мягко удаляет одну задачу после чтения, защитных проверок и точного `--confirm` для живого удаления.
- `linear-label-setup` создаёт отсутствующие метки только по явному запросу и ничего не делает с уже существующими метками.
- `linear-list-issues` читает списки задач для проверки метаданных без изменений Linear.
- `linear-update-issue` обновляет одну существующую задачу после чтения, включая priority или ручной `sortOrder`, и затем проверяет результат.
- `linear-custom-view-setup` создаёт один отсутствующий Custom View после проверки метаданных.
- `linear-custom-view-update` обновляет один существующий Custom View после чтения и затем проверяет результат.
- `linear-relation-setup` создаёт одну отсутствующую связь между задачами после чтения обеих задач и затем проверяет результат.

Они не решают, какую проектную задачу брать в работу, завершена ли доставка и можно ли ставить `Done`. Такие решения должны оставаться в проектном wrapper-навыке или процессном документе. Wrapper может вызывать эти скрипты через `LINEAR_API_KEY`, `LINEAR_ENV_FILE` или `--env-file`.

## Agent Approvals

Скрипты обращаются к Linear API, поэтому агентный рантайм может запросить сетевое разрешение. Чтобы не подтверждать одно и то же много раз, разрешайте только узкие префиксы (пример — для Codex; то же правило узких префиксов действует для Claude Code, Cursor, Antigravity, Windsurf и любого рантайма с моделью разрешений):

```text
python3 linear-change-status/scripts/change_status.py
python3 linear-comment-issue/scripts/comment_issue.py
python3 linear-create-issue/scripts/create_issue.py
python3 linear-delete-issue/scripts/delete_issue.py
python3 linear-custom-view/scripts/custom_view.py
python3 linear-custom-view-setup/scripts/custom_view_setup.py
python3 linear-custom-view-update/scripts/custom_view_update.py
python3 linear-label-setup/scripts/label_setup.py
python3 linear-list-issues/scripts/list_issues.py
python3 linear-read-issue/scripts/read_issue.py
python3 linear-relation-setup/scripts/relation_setup.py
python3 linear-update-issue/scripts/update_issue.py
```

Не разрешайте широкий префикс `python3`.

Подробная инструкция и готовый rules snippet лежат в [`docs/codex-approvals.md`](docs/codex-approvals.md).

## Модель безопасности

- API-ключ читается только из переменных окружения или локального env-файла.
- Скрипты не печатают API-ключ.
- `linear-change-status` сначала читает задачу, находит статус в команде этой задачи, обновляет только при необходимости и затем проверяет результат.
- `linear-change-status --dry-run` проверяет переход без изменения Linear.
- `linear-custom-view` сначала ищет Custom View по прямому ID или slug ID через `customView(id:)`, а затем при необходимости переходит к списку view рабочей области.
- `linear-custom-view` сохраняет ручной порядок Linear через `manual` sort.
- `linear-read-issue` отправляет только запросы чтения и никогда не отправляет GraphQL mutations.
- `linear-list-issues` отправляет только запросы чтения и никогда не отправляет GraphQL mutations.
- `linear-create-issue --dry-run` проверяет команду, статус, проект и метки без создания задачи.
- `linear-comment-issue --dry-run` проверяет целевую задачу без создания комментария.
- `linear-delete-issue --dry-run` читает целевую задачу и защитные проверки без удаления.
- `linear-delete-issue` мягко удаляет ровно одну задачу, требует точный `--confirm` и не поддерживает безвозвратное удаление.
- `linear-create-issue --optional-label` пропускает отсутствующие необязательные метки, но сохраняет ошибку для обязательных меток.
- `linear-create-issue` может назначить ответственного и родительскую задачу после проверки их ID; отсутствующие метки он не создаёт.
- `linear-label-setup --dry-run` проверяет команду и метки без создания меток.
- `linear-list-issues --without-labels` возвращает только задачи, у которых `labels.nodes` пустой.
- `linear-list-issues --missing-label` возвращает задачи, у которых нет хотя бы одной указанной метки.
- `linear-update-issue` сначала читает задачу, затем обновляет метки, ответственного, родителя, заголовок, описание или `sortOrder` и проверяет результат.
- `linear-update-issue --dry-run` проверяет целевое изменение без обновления Linear.
- `linear-update-issue --sort-order` меняет общий ручной порядок задач Linear; перед живой пачкой нужен dry-run и полная проверка Custom View.
- `linear-custom-view-setup --dry-run` проверяет команду, проект, метки и существующий Custom View без создания Custom View.
- `linear-custom-view-update --dry-run` проверяет метаданные и фильтры Custom View без обновления Linear.
- `linear-custom-view-update` не меняет ручной порядок задач.
- `linear-relation-setup --dry-run` читает обе задачи и существующие связи без создания связи.
- `linear-relation-setup` поддерживает `related`, `blocks` и `blocked-by`; `blocked-by` сохраняется как обратная связь `blocks`.
- Все скрипты используют общий GraphQL-клиент, единое чтение API-ключа, TLS через `certifi` при наличии пакета и очистку ошибок от токенов.

## Разработка

CI запускается на pull request, push в `main` и вручную через GitHub Actions. CI не ходит в настоящий Linear API и не требует `LINEAR_API_KEY`; тесты должны использовать локальные моки и фикстуры.

Локальный аналог CI:

```bash
scripts/validate.sh
```

Только тесты:

```bash
python3 -m unittest discover -s tests
```

Проверка секретов:

```bash
scripts/secret_scan.sh
```

`scripts/validate.sh` также блокирует случайные проектные или локальные машинные строки, чтобы публичный репозиторий оставался переносимым.

Локальный release gate после commit и push:

```bash
scripts/release_check.sh
```

Порядок релиза описан в [`docs/release.md`](docs/release.md). Обновления зависимостей ведёт Dependabot для GitHub Actions и Python requirements.

## Участие

См. [`CONTRIBUTING.md`](CONTRIBUTING.md).

## История изменений

См. [`CHANGELOG.md`](CHANGELOG.md).

## Безопасность

См. [`SECURITY.md`](SECURITY.md).

## Лицензия

MIT. См. [`LICENSE`](LICENSE).

## Отказ от принадлежности

Проект не связан с Linear. Он использует публичный Linear GraphQL API с личным API-ключом пользователя.
