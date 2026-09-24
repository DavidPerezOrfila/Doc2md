# Doc2md

> **Drop a document. Get clean Markdown.** Doc2md watches your input folder,
> converts office files and PDFs with Microsoft MarkItDown, repairs structural
> issues, and publishes only strict PyMarkdown-clean output.

Doc2md is a local-first document conversion pipeline for developers, data
teams, and automation workflows that need reliable Markdown without manual
cleanup.

## Features

- Converts PDF, Word, PowerPoint, Excel, HTML, EPUB, ZIP, and text formats.
- Watches `input/` and converts new or modified files automatically.
- Repairs headings, lists, links, URLs, tables, front matter, and code blocks.
- Rejects generated Markdown unless `pymarkdown scan` reports zero warnings.
- Quarantines unfixable output instead of publishing invalid Markdown.
- Blocks audio/video processing and unsafe archive expansion.
- Closes automatically after 30 seconds without new input.

## Requirements

- Windows
- Python 3.12 to 3.14

## Quick start

```bat
setup.bat
run_converter.bat
```

Copy documents into `input/`. Clean Markdown appears in `converted/` as
`document.pdf.md`, `document.docx.md`, and so on. The service exits after 30
seconds without a new input file.

## Workflow

1. `watchdog` detects a stable local file.
2. MarkItDown extracts its content locally.
3. The repair pipeline fixes Markdown structure and degrades unrecoverable
   tables to readable text blocks.
4. PyMarkdown runs in strict mode.
5. Only zero-warning output is atomically published to `converted/`.

## Development

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\pymarkdown.exe --config .pymarkdown.json --strict-config scan converted\*.md
```

The application lives in `src/doc2md/`, with separate modules for conversion,
repair, validation, archive safety, output, and filesystem watching.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
