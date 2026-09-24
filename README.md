<div align="center">

# ✨ Doc2md

## Drop a document. Get clean Markdown.

**Doc2md watches your folder, converts complex documents, repairs the output, and publishes only zero-warning Markdown.**

[![CI](https://github.com/DavidPerezOrfila/Doc2md/actions/workflows/ci.yml/badge.svg)](https://github.com/DavidPerezOrfila/Doc2md/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/DavidPerezOrfila/Doc2md?label=Release&color=blue)](https://github.com/DavidPerezOrfila/Doc2md/releases/latest)
[![License](https://img.shields.io/github/license/DavidPerezOrfila/Doc2md?color=blue)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12--3.14-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

[⬇ Download Doc2md for Windows](https://github.com/DavidPerezOrfila/Doc2md/releases/latest/download/Doc2md-Windows-x64.zip)

</div>

---

## 🚀 What it does

|                |                                                                           |
| -------------- | ------------------------------------------------------------------------- |
| 📥 **Drop**     | Place PDF, DOCX, PPTX, XLSX, EPUB, HTML, ZIP, or text files into `input/` |
| ⚙️ **Convert**  | MarkItDown extracts content locally with no cloud processing              |
| 🧹 **Repair**   | Doc2md fixes headings, lists, links, URLs, tables, code, and front matter |
| ✅ **Validate** | PyMarkdown strict mode must return **zero warnings**                      |
| 📦 **Publish**  | Only clean Markdown is atomically written to `converted/`                 |
| 😴 **Finish**   | The watcher exits after 30 seconds without new input                      |

## 🧭 Workflow

```text
input/
   │
   ▼
┌──────────────────────┐
│ Local file detection │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ MarkItDown converter  │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Markdown repair      │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Strict PyMarkdown     │──fail──▶ converted/.quarantine/
└──────────┬───────────┘
           │ zero warnings
           ▼
      converted/*.md
```

## ✨ Highlights

- 🔒 **Local-first:** no document content is uploaded.
- 🧠 **Structure-aware repair:** fixes real Markdown semantics, not only whitespace.
- 🧯 **Archive protection:** rejects ZIP bombs, nested archives, and unsafe media.
- ♻️ **Resilient output:** restores the previous valid result after a failed refresh.
- 🧱 **Modular:** conversion, validation, repair, output, and watching are independent.
- 🪶 **No-warning guarantee:** invalid Markdown is quarantined instead of published.
- ⏱️ **Zero idle time:** automatically closes after 30 seconds without input.

## ⬇️ Download

1. Open the [latest release](https://github.com/DavidPerezOrfila/Doc2md/releases/latest).
2. Download `Doc2md-Windows-x64.zip`.
3. Extract it anywhere on your Windows computer.
4. Keep `Doc2md.exe` and `pymarkdown.exe` in the same folder.
5. Create `input/` and `converted/` beside the executables.
6. Run `Doc2md.exe`.

## 🛠️ Run from source

**Requirements:** Windows and Python 3.12–3.14.

```bat
setup.bat
run_converter.bat
```

Copy documents into `input/`. Clean output appears in `converted/` as
`document.pdf.md`, `document.docx.md`, and so on.

## 🧪 Development

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\pymarkdown.exe --config .pymarkdown.json --strict-config scan converted\*.md
```

## 📄 License

**Apache License 2.0** — permissive, commercial-friendly, and includes an
express patent grant. See [`LICENSE`](LICENSE).
