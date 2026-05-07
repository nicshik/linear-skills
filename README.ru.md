# Linear Skills

[English](README.md)

Codex-навыки и небольшие Python-скрипты для прямой работы с Linear GraphQL API.

Репозиторий полезен, когда стандартный Linear connector недоступен, работает только на чтение или не может выполнить узкое действие, но нужен проверяемый способ автоматизировать Linear через личный API-ключ пользователя.

Репозиторий намеренно универсальный. Проектные очереди, правила доставки, префиксы задач и решение о переводе в `Done` должны жить в отдельном проектном wrapper-навыке или проектной документации.

## Что входит

| Навык | Назначение |
| --- | --- |
| `linear-custom-view` | Читает Linear Custom View и возвращает задачи в ручном порядке Linear. |
| `linear-change-status` | Меняет статус Linear-задачи и проверяет итог. |

## Структура

```text
linear-change-status/
  SKILL.md
  agents/openai.yaml
  scripts/change_status.py
linear-custom-view/
  SKILL.md
  agents/openai.yaml
  scripts/custom_view.py
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

Они не решают, какую проектную задачу брать в работу, завершена ли доставка и можно ли ставить `Done`. Такие решения должны оставаться в проектном wrapper-навыке или процессном документе. Wrapper может вызывать эти скрипты через `LINEAR_API_KEY`, `LINEAR_ENV_FILE` или `--env-file`.

## Codex Approvals

Скрипты обращаются к Linear API, поэтому Codex может запросить сетевое разрешение. Чтобы не подтверждать одно и то же много раз, разрешайте только узкие префиксы:

```text
python3 linear-change-status/scripts/change_status.py
python3 linear-custom-view/scripts/custom_view.py
```

Не разрешайте широкий префикс `python3`.

Подробная инструкция и готовый rules snippet лежат в [`docs/codex-approvals.md`](docs/codex-approvals.md).

## Модель безопасности

- API-ключ читается только из переменных окружения или локального env-файла.
- Скрипты не печатают API-ключ.
- `linear-change-status` сначала читает задачу, находит статус в команде этой задачи, обновляет только при необходимости и затем проверяет результат.
- `linear-change-status --dry-run` проверяет переход без изменения Linear.
- `linear-custom-view` сохраняет ручной порядок Linear через `manual` sort.

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
