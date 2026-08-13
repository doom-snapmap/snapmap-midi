"""Find identifiers the workstation's Javascript reads but never declares.

The rest of the suite checks that `app.js` CONTAINS the right text. That
cannot notice a rename that missed one use: the file still parses, still
contains every string the assertions look for, and throws `ReferenceError`
the first time the missed line runs. When that line is inside the render
path the whole window stops responding -- every button dead, no error
anywhere a user can see -- and the suite stays green throughout.

This is a scanner, not a parser. It strips comments, strings and regex
literals, collects every declaration in the file, and reports identifiers
used that match none of them. File-wide rather than per-scope, so it will
not catch a name declared in one function and used in another -- but it
does catch the rename that leaves a name declared nowhere at all, which is
the mistake that shipped a dead window.
"""

import re
import sys
from pathlib import Path

KEYWORDS = {
    "var",
    "let",
    "const",
    "function",
    "return",
    "if",
    "else",
    "for",
    "while",
    "do",
    "break",
    "continue",
    "new",
    "delete",
    "typeof",
    "instanceof",
    "in",
    "of",
    "this",
    "null",
    "true",
    "false",
    "undefined",
    "void",
    "throw",
    "try",
    "catch",
    "finally",
    "switch",
    "case",
    "default",
    "arguments",
    "class",
    "extends",
    "super",
    "yield",
    "await",
    "async",
    "static",
    "get",
    "set",
}

GLOBALS = {
    "window",
    "document",
    "console",
    "Math",
    "JSON",
    "Number",
    "String",
    "Boolean",
    "Array",
    "Object",
    "Promise",
    "Date",
    "RegExp",
    "Error",
    "Set",
    "Map",
    "WeakMap",
    "setTimeout",
    "clearTimeout",
    "setInterval",
    "clearInterval",
    "isFinite",
    "isNaN",
    "parseInt",
    "parseFloat",
    "requestAnimationFrame",
    "cancelAnimationFrame",
    "performance",
    "navigator",
    "localStorage",
    "sessionStorage",
    "fetch",
    "NaN",
    "Infinity",
    "encodeURIComponent",
    "decodeURIComponent",
    "escape",
    "unescape",
    "AudioContext",
    "webkitAudioContext",
    "Uint8Array",
    "Float32Array",
    "Int16Array",
    "ArrayBuffer",
    "DataView",
    "Blob",
    "URL",
    "URLSearchParams",
    "XMLHttpRequest",
    "CustomEvent",
    "Event",
    "DOMParser",
    "atob",
    "btoa",
    "alert",
    "confirm",
    "prompt",
    "getComputedStyle",
    "HTMLElement",
    "SVGElement",
    "Image",
    "FileReader",
    "Symbol",
    "globalThis",
    "self",
    "top",
    "parent",
    "location",
    "history",
    "screen",
    "ResizeObserver",
    "MutationObserver",
    "IntersectionObserver",
}

# A slash begins a regex literal only where a value may begin. Anywhere else it
# is division. Character classes inside a regex are full of bare letters, which
# would otherwise read as undeclared identifiers.
_REGEX_LITERAL = re.compile(
    r"(?<=[(,=:\[!&|?{};+\-*%^~])\s*"
    r"/(?:\\.|\[(?:\\.|[^\]\\])*\]|[^/\\\n])+/[gimsuy]*"
)


def strip(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    source = re.sub(r"//[^\n]*", " ", source)
    source = re.sub(r"'(?:\\.|[^'\\\n])*'", "''", source)
    source = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', source)
    source = re.sub(r"`(?:\\.|[^`\\])*`", "``", source)
    return _REGEX_LITERAL.sub(" 0 ", source)


def declared(source: str) -> set:
    names = set()
    for match in re.finditer(r"\bvar\s+([\w$]+(?:\s*,\s*[\w$]+)*)", source):
        for piece in match.group(1).split(","):
            names.add(piece.strip())
    for match in re.finditer(r"\b(?:let|const)\s+([\w$]+)", source):
        names.add(match.group(1))
    for match in re.finditer(r"\bfunction\s*([\w$]*)\s*\(([^)]*)\)", source):
        if match.group(1):
            names.add(match.group(1))
        for param in match.group(2).split(","):
            param = param.strip()
            if param:
                names.add(param)
    for match in re.finditer(r"\bcatch\s*\(\s*([\w$]+)", source):
        names.add(match.group(1))
    for match in re.finditer(r"\(([^()]*)\)\s*=>", source):
        for param in match.group(1).split(","):
            param = param.strip()
            if param:
                names.add(param)
    for match in re.finditer(r"\b([\w$]+)\s*=>", source):
        names.add(match.group(1))
    return names


def used(source: str) -> set:
    names = set()
    for match in re.finditer(r"([.\w$]?)\s*\b([A-Za-z_$][\w$]*)\b\s*(:?)", source):
        prefix, name, colon = match.group(1), match.group(2), match.group(3)
        if prefix == "." or colon == ":":
            continue
        names.add(name)
    return names


def undeclared(source: str) -> set:
    body = strip(source)
    return used(body) - declared(body) - KEYWORDS - GLOBALS


if __name__ == "__main__":  # pragma: no cover - a convenience for hand runs
    path = Path(sys.argv[1])
    missing = undeclared(path.read_text(encoding="utf-8"))
    print("undeclared in %s: %s" % (path.name, sorted(missing) or "none"))
