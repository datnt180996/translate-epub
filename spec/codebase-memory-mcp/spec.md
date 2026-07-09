# Codebase Memory MCP

## Muc tieu

`codebase-memory-mcp` tao mot "bo nho cau truc code" cho du an. Noi don gian:
thay vi AI phai doc tung file tu dau, MCP nay giup AI tim ham, route, quan he
goi ham, va tong quan kien truc nhanh hon.

## Thiet lap hien tai

- MCP da duoc cai bang installer chinh thuc tu repo
  `DeusData/codebase-memory-mcp`.
- Binary dung cho Codex/MCP duoc cai tai:
  `C:\Users\DATNT\.local\bin\codebase-memory-mcp.exe`.
- Binary co giao dien web UI duoc cai tai:
  `C:\Users\DATNT\AppData\Local\Programs\codebase-memory-mcp\codebase-memory-mcp.exe`.
- Codex config da co server:
  `[mcp_servers.codebase-memory-mcp]`.
- Du an nay da duoc index voi ten:
  `D-Work-Project-translate-epub`.
- Thu muc goc duoc index:
  `D:\Work\Project\translate-epub`.
- Che do index da dung:
  `moderate`.

## Hanh vi mong doi

- Sau khi restart Codex, MCP server se duoc nap tu cau hinh Codex.
- AI co the dung cac tool nhu `search_code`, `search_graph`,
  `get_architecture`, `trace_path`, va `get_code_snippet` de hieu code nhanh
  hon.
- Index hien tai la local tren may nay. Repo khong co artifact chia se
  `.codebase-memory/graph.db.zst`.
- De xem ban do truc quan, can chay binary UI va mo trinh duyet tai
  `http://localhost:9749`.

## Lenh huu ich

Kiem tra project da index:

```powershell
C:\Users\DATNT\.local\bin\codebase-memory-mcp.exe cli list_projects
```

Kiem tra trang thai index:

```powershell
C:\Users\DATNT\.local\bin\codebase-memory-mcp.exe cli index_status --project D-Work-Project-translate-epub
```

Index lai du an:

```powershell
C:\Users\DATNT\.local\bin\codebase-memory-mcp.exe cli index_repository --repo-path D:\Work\Project\translate-epub --mode moderate
```

Mo giao dien ban do web:

```powershell
C:\Users\DATNT\AppData\Local\Programs\codebase-memory-mcp\codebase-memory-mcp.exe --ui=true
```

Sau do mo:

```text
http://localhost:9749
```

## Gioi han

- Can restart Codex de MCP server moi xuat hien trong phien lam viec moi.
- Ban tai `C:\Users\DATNT\.local\bin\codebase-memory-mcp.exe` la ban standard
  nen co the khong mo duoc UI. Neu can xem ban do web, dung binary trong
  `C:\Users\DATNT\AppData\Local\Programs\codebase-memory-mcp\`.
- Neu code thay doi nhieu, nen chay lai lenh index de cap nhat bo nho.
- Tool nay doc code local va ghi cau hinh agent local. Khong thay the test cua
  du an.

## Kiem tra da thuc hien

- `codebase-memory-mcp --help`
- `codebase-memory-mcp config list`
- `codebase-memory-mcp cli index_repository --repo-path D:\Work\Project\translate-epub --mode moderate`
- `codebase-memory-mcp cli list_projects`
- `codebase-memory-mcp cli index_status --project D-Work-Project-translate-epub`
- `codebase-memory-mcp cli search_code --project D-Work-Project-translate-epub --pattern translate_chapter --limit 5`
- `codebase-memory-mcp cli get_architecture --project D-Work-Project-translate-epub --aspects overview`
- `C:\Users\DATNT\AppData\Local\Programs\codebase-memory-mcp\codebase-memory-mcp.exe --ui=true`
- `Invoke-WebRequest http://localhost:9749`
