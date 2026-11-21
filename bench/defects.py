"""replay の品質指標のうち、テストで測れない欠陥を数える(簡易な静的検査)。

数えるもの(いずれも base からの増分):
- empty_comments: 追加した行のうち、中身のない `#` だけのコメント(.py / .toml)
- unused_imports: import したのに、そのファイルで一度も参照しない名前
- unused_defs: 定義したのに、リポジトリのどの .py にも定義行以外で名前が現れない関数・クラス
- extra_files: 再現対象の commit が触っていないファイルへの変更(仕様外の変更の目安)
ruff などの外部ツールを使わないのは、依存を増やさず、オフラインでも同じ結果にするため。
名前の一致だけで判定するので、getattr などの動的な参照は見逃し、同名の別物は参照ありと数える。
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

EMPTY_COMMENT = re.compile(r"^\+\s*#\s*$")
SKIP_DEF = re.compile(r"^(__\w+__|main|setUp\w*|tearDown\w*|test\w*)$")


def _git(wt: Path, *a: str) -> str:
    return subprocess.run(["git", *a], cwd=wt, capture_output=True, text=True).stdout


def changed_files(wt: Path, base: str) -> list[str]:
    _git(wt, "add", "-A", "-N")  # 新規ファイルも差分に出す
    return [p for p in _git(wt, "diff", "--name-only", base).splitlines() if "__pycache__" not in p]


def empty_comments(diff: str) -> int:
    n, cur = 0, ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else ""
            continue
        if cur.endswith((".py", ".toml")) and EMPTY_COMMENT.match(line):
            n += 1
    return n


def _unused_imports(src: str) -> int:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return 0
    imported: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported[(a.asname or a.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            for a in node.names:
                if a.name != "*":
                    imported[a.asname or a.name] = node.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    # 文字列の型注釈や __all__ の中の名前も参照として数える
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            used.update(re.findall(r"[A-Za-z_]\w*", n.value))
    lines = src.splitlines()
    return sum(1 for name, ln in imported.items()
               if name not in used and "noqa" not in lines[ln - 1])


def _defs(src: str) -> set[str]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()
    return {n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not SKIP_DEF.match(n.name)}


def _all_py(wt: Path, rev: str | None) -> str:
    if rev is None:
        files = [p for p in _git(wt, "ls-files", "-co", "--exclude-standard").splitlines() if p.endswith(".py")]
        return "\n".join((wt / p).read_text(errors="replace") for p in files if (wt / p).is_file())
    files = [p for p in _git(wt, "ls-tree", "-r", "--name-only", rev).splitlines() if p.endswith(".py")]
    return "\n".join(_git(wt, "show", f"{rev}:{p}") for p in files)


def _unused_defs(names: set[str], corpus: str) -> int:
    # 定義行(def/class の行)を除いて名前が 1 度も現れなければ未使用とみなす
    body = re.sub(r"^\s*(?:async\s+)?(?:def|class)\s+\w+", "", corpus, flags=re.M)
    return sum(1 for n in names if not re.search(rf"\b{re.escape(n)}\b", body))


def strip_files(diff: str, exclude: list[str]) -> str:
    """git diff の出力から、exclude のファイルの節を取り除く。"""
    keep, out = True, []
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            keep = not any(line.rstrip().endswith(f" b/{p}") for p in exclude)
        if keep:
            out.append(line)
    return "".join(out)


def count(wt: Path, base: str, target_files: list[str], exclude: list[str] = ()) -> dict:
    """exclude(完成形として渡したテストなど)は数えない。どの条件でも同じ中身なので差が出ないため。"""
    files = [p for p in changed_files(wt, base) if p not in exclude]
    diff = strip_files(_git(wt, "diff", base), list(exclude))
    res = {"files_changed": len(files), "lines_changed": 0, "empty_comments": empty_comments(diff),
           "unused_imports": 0, "unused_defs": 0,
           "extra_files": sorted(set(files) - set(target_files))}
    res["lines_changed"] = sum(1 for line in diff.splitlines()
                               if line[:1] in "+-" and not line.startswith(("+++", "---")))
    now_corpus, base_corpus = _all_py(wt, None), _all_py(wt, base)
    for p in files:
        if not p.endswith(".py"):
            continue
        path = wt / p
        new = path.read_text(errors="replace") if path.is_file() else ""
        old = _git(wt, "show", f"{base}:{p}")
        res["unused_imports"] += max(0, _unused_imports(new) - _unused_imports(old))
        res["unused_defs"] += max(0, _unused_defs(_defs(new), now_corpus) - _unused_defs(_defs(old), base_corpus))
    res["total"] = res["empty_comments"] + res["unused_imports"] + res["unused_defs"] + len(res["extra_files"])
    return res
