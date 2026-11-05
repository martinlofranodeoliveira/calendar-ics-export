<!-- public-docs-pt:v1 -->
# Exportador de calendários ICS

Converte eventos JSON em arquivos iCalendar determinísticos, com horários UTC explícitos e exemplos fictícios.

**Estado:** edição pública de desenvolvimento. Recursos e limites detalhados estão na referência técnica preservada abaixo.

## Começar em português

**Requisitos:** Python 3.10+; biblioteca padrão.

```sh
git clone https://github.com/martinlofranodeoliveira/calendar-ics-export.git
cd calendar-ics-export
python -m calendar_ics_export examples/workshop.json > workshop.ics
```

Use um ambiente de desenvolvimento separado. Não envie `.env`, chaves, bancos,
uploads ou dados pessoais ao Git. Nas demonstrações, use somente dados fictícios.

## Documentação e validação

[Licença](LICENSE) · [Catálogo do laboratório](https://github.com/martinlofranodeoliveira#projetos-abertos)

Os comandos acima foram conferidos nos manifests/guia público; não significam que todas as integrações, plataformas ou serviços reais foram exercitados nesta revisão documental.

A referência técnica original abaixo preserva APIs, exemplos, limites e histórico
de funcionalidades. Auxiliares em `community/` são módulos independentes: sua
existência não comprova integração na interface ou no fluxo principal. Ao avaliar
uma funcionalidade, consulte também o teste e o código do módulo correspondente.

## Contribuir

Abra uma issue com objetivo, comportamento observado, versão e um exemplo mínimo
sintético. Para código, inclua testes relevantes, instruções de reprodução e
atualização da documentação. Não envie segredos ou informações de terceiros em
issues, exemplos, capturas ou pull requests. Mudanças úteis e completas têm
preferência sobre alterações feitas apenas para aumentar atividade.

## Licença e autoria

Licença declarada no repositório: **MIT**. Consulte o arquivo de licença e mantenha as atribuições de terceiros.

Nome técnico e URL preservados para manter imports, links e automações existentes.
Título, descrição e tópicos em português facilitam localizar a finalidade do projeto.

<!-- public-docs-pt:end -->

---

## Referência técnica e documentação original

# calendar-ics-export

Turn a small JSON event list into a deterministic `.ics` file for a calendar
import, a static event feed, or a reproducible build. Python 3.10+; no runtime
dependencies, network access, account, or service required.

**Português:** converta uma lista de eventos JSON em um arquivo `.ics`
reproduzível. A ferramenta funciona localmente, usa apenas a biblioteca padrão
do Python e aceita somente horários UTC explícitos. O exemplo é totalmente
sintético.

## Quick start

From a checkout, without installation:

```sh
python -m calendar_ics_export examples/workshop.json > workshop.ics
```

Or install locally and use the console command:

```sh
python -m pip install .
calendar-ics-export examples/workshop.json > workshop.ics
```

To read a pipeline, explicitly select stdin:

```sh
cat examples/workshop.json | python -m calendar_ics_export - > workshop.ics
```

The CLI reads at most **4 MiB** of UTF-8 JSON, validates the entire document,
then writes ICS bytes to stdout. It rejects duplicate JSON keys and nonfinite
JSON constants. Exit status is `0` for success or `2` for invalid arguments,
input, or an I/O error. Diagnostics go to stderr without echoing input content
or file paths. Shell redirection creates or truncates its destination before
the command runs; failed validation produces no stdout bytes.

## Input contract

```json
{
  "stamp": "2026-10-25T12:00:00Z",
  "events": [
    {
      "uid": "demo-01@example.invalid",
      "start": "2026-11-03T14:00:00Z",
      "end": "2026-11-03T15:00:00Z",
      "summary": "Map workshop",
      "description": "Bring a laptop.\nAll details are synthetic.",
      "location": "Community room A"
    }
  ]
}
```

| Field | Requirement |
| --- | --- |
| Document | An object with exactly `stamp` and `events`. |
| `stamp` | A real UTC timestamp, exactly `YYYY-MM-DDTHH:MM:SSZ`; used as every event's `DTSTAMP`. |
| `events` | A list containing zero to 10,000 events. |
| Event | Exactly `uid`, `start`, `end`, `summary`, plus optional `description` and `location`. |
| `uid` | Unique, case-sensitive identifier of 1–255 ASCII characters from `A-Z`, `a-z`, `0-9`, `@`, `.`, `_`, `-`. |
| `start`, `end` | Real timestamps in the same exact UTC format, with `start < end`. |
| `summary` | A nonempty string. |
| `description`, `location` | Strings; empty strings are accepted and retained when supplied. |

Unknown or missing fields are errors. Dates, offsets, fractional seconds,
leap seconds, timezone names, and year zero are rejected. Text rejects Unicode
surrogates and control characters except tab, carriage return, and line feed.
Keep a UID stable between exports when it identifies the same event. Reuse an
explicit stamp to get identical bytes; the exporter never reads the clock.

## Python API

```python
import json
from pathlib import Path

from calendar_ics_export import CalendarError, export_calendar

document = json.loads(Path("examples/workshop.json").read_text(encoding="utf-8"))
try:
    ics_bytes = export_calendar(document)
except CalendarError as error:
    print(error)
else:
    Path("workshop.ics").write_bytes(ics_bytes)
```

`export_calendar(document) -> bytes` validates a `dict` with an `events` list,
preserves the input, and raises `CalendarError` on schema violations. For JSON
files requiring the CLI's duplicate-key and byte-limit checks, use the CLI;
ordinary `json.loads` overwrites duplicate keys before the API sees them.

## Output and scope

The output is a deliberately small **UTC-only VEVENT export subset**, not a
calendar parser or a scheduling service. It has no recurrence, all-day dates,
alarms, attendees, attachments, local time conversion, invitations, updates,
or synchronization. Calendar applications decide how imports with an existing
UID are handled. Event end times are exclusive.

Events are sorted by ASCII UID. Each event emits `UID`, `DTSTAMP`, `DTSTART`,
`DTEND`, `SUMMARY`, then optional `DESCRIPTION` and `LOCATION` in that order.
The fixed calendar header is `BEGIN:VCALENDAR`, `VERSION:2.0`,
`PRODID:-//Lofrano Open Source//calendar-ics-export 0.1//EN`, and
`CALSCALE:GREGORIAN`, followed by events and `END:VCALENDAR`.

Text normalizes CRLF and bare CR to LF, then escapes backslashes, semicolons,
commas, and newlines. Content uses UTF-8 and CRLF line endings, including the
final newline. Physical lines contain at most 75 bytes, counting continuation
spaces; folding never cuts a UTF-8 code point. Text newlines stay inside their
property value and cannot inject new calendar properties.

The format reference is [RFC 5545](https://www.rfc-editor.org/rfc/rfc5545.html),
especially [section 3.1: content lines](https://www.rfc-editor.org/rfc/rfc5545.html#section-3.1)
and [section 3.3.11: text](https://www.rfc-editor.org/rfc/rfc5545.html#section-3.3.11).
The implementation is original Python code, not copied RFC code or examples.

## Development

```sh
python -m unittest discover -s tests -v
```

Tests use only synthetic data and Python's standard library. They cover exact
output, schema rejection, dates, escaping, multibyte folding, injection
attempts, determinism, input preservation, CLI limits, and sanitized failures.
CI runs on Python 3.10, 3.12, and 3.14. The API event-count limit is not a total
text-size limit; callers accepting untrusted in-memory objects should apply
their own input-size budget.

MIT licensed; see [LICENSE](LICENSE).
