# pyright: reportAny=none,reportUnannotatedClassAttribute=none

from __future__ import annotations

import abc
import argparse
import contextlib
import dataclasses
import enum
import hashlib
import json
import sys
from abc import abstractmethod
from typing import (
    Any,
    ClassVar,
    Literal,
    NotRequired,
    TextIO,
    TypedDict,
    cast,
    override,
)

import schema as s


class Severity(enum.Enum):
    NONE = 0
    DEBUG = enum.auto()
    INFO = enum.auto()
    WARN = enum.auto()
    ERROR = enum.auto()
    CRIT = enum.auto()


@dataclasses.dataclass(frozen=True)
class AnnotationItem:
    tool_id: str
    path: str
    start_line: int | None
    end_line: int | None
    start_col: int | None
    end_col: int | None
    level: Severity
    title: str | None
    message: str
    detail: str | None = dataclasses.field(default=None, repr=False)
    href: str | None = dataclasses.field(default=None, repr=False)
    fingerprint: str = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        m = hashlib.md5(usedforsecurity=False)
        m.update(repr(self).encode(encoding="utf-8"))
        object.__setattr__(self, "fingerprint", m.hexdigest())


class InputAdapter(abc.ABC):
    registry: ClassVar[dict[str, type[InputAdapter]]] = {}
    id: ClassVar[str]
    schema: ClassVar[s.Schema]
    severity_map: ClassVar[dict[str, Severity]]

    @classmethod
    @abstractmethod
    def from_file(cls, infile: TextIO) -> list[AnnotationItem]:
        pass

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        cls.registry[cls.id] = cls


class OutputAdapter(abc.ABC):
    registry: ClassVar[dict[str, type[OutputAdapter]]] = {}
    id: ClassVar[str]
    severity_map: ClassVar[dict[Severity, str]]

    @classmethod
    @abstractmethod
    def to_file(cls, annotations: list[AnnotationItem], outfile: TextIO) -> None:
        pass

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        cls.registry[cls.id] = cls


class PyrightAdapter(InputAdapter):
    id = "pyright"

    schema = s.Schema({
        "file": str,
        "severity": s.Or(
            s.Schema("information"),
            s.Schema("warning"),
            s.Schema("error"),
        ),
        "message": str,
        "range": {
            "start": {"line": int, "character": int},
            "end": {"line": int, "character": int},
        },
        s.Optional("rule"): str,
    })

    severity_map = {
        "information": Severity.INFO,
        "warning": Severity.WARN,
        "error": Severity.ERROR,
    }

    @override
    @classmethod
    def from_file(cls, infile: TextIO) -> list[AnnotationItem]:
        class _PyrightDiagPosition(TypedDict):
            line: int
            character: int

        class _PyrightDiagRange(TypedDict):
            start: _PyrightDiagPosition
            end: _PyrightDiagPosition

        class _PyrightDiagItem(TypedDict):
            file: str
            severity: Literal["information", "warning", "error"]
            message: str
            range: _PyrightDiagRange
            rule: NotRequired[str]

        report = json.load(infile)
        result: list[AnnotationItem] = []
        for item in report["generalDiagnostics"]:
            diag = cast(_PyrightDiagItem, cls.schema.validate(item))
            anno_item = AnnotationItem(
                cls.id,
                diag["file"],
                diag["range"]["start"]["line"] + 1,
                diag["range"]["end"]["line"] + 1,
                diag["range"]["start"]["character"] + 1,
                diag["range"]["end"]["character"] + 1,
                cls.severity_map[diag["severity"]],
                diag["rule"] if "rule" in diag else "",
                diag["message"],
            )
            result.append(anno_item)
        return result


class BasedpyrightAdapter(PyrightAdapter):
    id = "basedpyright"


class PyreflyAdapter(InputAdapter):
    id = "pyrefly"

    schema = s.Schema({
        "line": int,
        "column": int,
        "stop_line": int,
        "stop_column": int,
        "path": str,
        "code": int,
        "name": str,
        "description": str,
        "concise_description": str,
        "severity": s.Or(
            s.Schema("info"),
            s.Schema("warning"),
            s.Schema("error"),
        ),
    })

    severity_map = {
        "info": Severity.INFO,
        "warning": Severity.WARN,
        "error": Severity.ERROR,
    }

    @override
    @classmethod
    def from_file(cls, infile: TextIO) -> list[AnnotationItem]:
        class _PyreflyDiagItem(TypedDict):
            line: int
            column: int
            stop_line: int
            stop_column: int
            path: str
            code: int
            name: str
            description: str
            concise_description: str
            severity: Literal["info", "warning", "error"]

        report = json.load(infile)
        result: list[AnnotationItem] = []
        for item in report["errors"]:
            diag = cast(_PyreflyDiagItem, cls.schema.validate(item))
            anno_item = AnnotationItem(
                cls.id,
                diag["path"],
                diag["line"],
                diag["stop_line"],
                diag["column"],
                diag["stop_column"],
                cls.severity_map[diag["severity"]],
                diag["name"],
                diag["concise_description"],
                diag["description"],
            )
            result.append(anno_item)
        return result


class MypyAdapter(InputAdapter):
    id = "mypy"

    schema = s.Schema({
        "file": str,
        "line": int,
        "column": int,
        "message": str,
        "hint": s.Or(str, s.Schema(None)),
        "code": s.Or(str, s.Schema(None)),
        "severity": s.Or(
            s.Schema("note"),
            s.Schema("warning"),
            s.Schema("error"),
        ),
    })

    severity_map = {
        "note": Severity.INFO,
        "warning": Severity.WARN,
        "error": Severity.ERROR,
    }

    @override
    @classmethod
    def from_file(cls, infile: TextIO) -> list[AnnotationItem]:
        class _MypyDiagItem(TypedDict):
            file: str
            line: int
            column: int
            message: str
            hint: str | None
            code: str | None
            severity: Literal["note", "warning", "error"]

        json_str = "[" + ",".join([line.strip() for line in infile.readlines()]) + "]"
        result: list[AnnotationItem] = []
        for item in json.loads(json_str):
            diag = cast(_MypyDiagItem, cls.schema.validate(item))
            anno_item = AnnotationItem(
                cls.id,
                diag["file"],
                diag["line"],
                None,  # only available with --show-error-end and text output
                diag["column"] + 1,  # WTF
                None,
                cls.severity_map[diag["severity"]],
                diag["code"],
                diag["message"],
                diag["hint"] or None,
            )
            result.append(anno_item)
        return result


class TyAdapter(InputAdapter):
    id = "ty"

    schema = s.Schema({
        "check_name": str,
        "description": str,
        "severity": s.Or(
            s.Schema("info"),
            s.Schema("minor"),
            s.Schema("major"),
            s.Schema("critical"),
        ),
        "fingerprint": str,
        "location": {
            "path": str,
            "positions": {
                "begin": {
                    "line": int,
                    "column": int,
                },
                "end": {
                    "line": int,
                    "column": int,
                },
            },
        },
    })

    severity_map = {
        "info": Severity.INFO,
        "minor": Severity.WARN,
        "major": Severity.ERROR,
        "critical": Severity.CRIT,
    }

    @override
    @classmethod
    def from_file(cls, infile: TextIO) -> list[AnnotationItem]:
        class _TyDiagPosition(TypedDict):
            line: int
            column: int

        class _TyDiagLocation(TypedDict):
            path: str
            positions: dict[Literal["begin", "end"], _TyDiagPosition]

        class _TyDiagItem(TypedDict):
            check_name: str
            description: str
            severity: Literal["info", "minor", "major", "critical"]
            fingerprint: str
            location: _TyDiagLocation

        report = json.load(infile)
        result: list[AnnotationItem] = []
        for item in report:
            diag = cast(_TyDiagItem, cls.schema.validate(item))
            begin_pos = diag["location"]["positions"]["begin"]
            end_pos = diag["location"]["positions"]["end"]
            anno_item = AnnotationItem(
                cls.id,
                diag["location"]["path"],
                begin_pos["line"],
                end_pos["line"],
                begin_pos["column"],
                end_pos["column"],
                cls.severity_map[diag["severity"]],
                diag["check_name"],
                diag["description"],
            )
            object.__setattr__(anno_item, "fingerprint", diag["fingerprint"])
            result.append(anno_item)
        return result


class GitHubJsonAdapter(OutputAdapter):
    id = "github-json"

    severity_map = {
        Severity.DEBUG: "debug",
        Severity.INFO: "notice",
        Severity.WARN: "warning",
        Severity.ERROR: "error",
    }

    @override
    @classmethod
    def to_file(cls, annotations: list[AnnotationItem], outfile: TextIO) -> None:
        result: list[dict[str, str | int | None]] = []
        for item in annotations:
            if item.level.value < Severity.WARN.value:
                continue
            anno_item = {
                "path": item.path,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "start_column": item.start_col,
                "end_column": item.end_col,
                "annotation_level": cls.severity_map[item.level],
                "title": (
                    f"{item.tool_id} ({item.title})" if item.title else item.tool_id
                ),
                "message": item.message,
                "raw_details": item.detail,
                "blob_href": item.href,
            }
            result.append(anno_item)
        json.dump(result, outfile, indent=2)


class GitHubTextAdapter(OutputAdapter):
    id = "github-text"

    severity_map = {
        Severity.DEBUG: "debug",
        Severity.INFO: "notice",
        Severity.WARN: "warning",
        Severity.ERROR: "error",
    }

    @override
    @classmethod
    def to_file(cls, annotations: list[AnnotationItem], outfile: TextIO) -> None:
        for item in annotations:
            if item.level.value < Severity.WARN.value:
                continue
            optional_params: list[str] = []
            optional_params.append(f"file={item.path.replace(chr(92), '\\\\')}")
            if item.start_line is not None:
                optional_params.append(f"line={item.start_line}")
            if item.start_col is not None:
                optional_params.append(f"col={item.start_col}")
            if item.end_line is not None:
                optional_params.append(f"endLine={item.end_line}")
            if item.end_col is not None:
                optional_params.append(f"endColumn={item.end_col}")
            title = f"{item.tool_id} ({item.title})" if item.title else item.tool_id
            optional_params.append(
                f"title={title.replace("\r", '').replace("\n", ' ')}"
            )
            message = item.message + (f"\n{item.detail}" if item.detail else "")

            formatted_message = "::{} {}::{}\n".format(
                cls.severity_map[item.level],
                ",".join(optional_params),
                message.replace("\n", "%0A"),
            )
            _ = outfile.write(formatted_message)


class GitLabCodeQualityAdapter(OutputAdapter):
    id = "gitlab-json"

    severity_map = {
        Severity.INFO: "info",
        Severity.WARN: "minor",
        Severity.ERROR: "major",
    }

    @override
    @classmethod
    def to_file(cls, annotations: list[AnnotationItem], outfile: TextIO) -> None:
        gl_annotations: list[dict[str, Any]] = []
        for item in annotations:
            if item.level.value < Severity.WARN.value:
                continue
            anno_item: dict[str, Any] = {
                "description": item.message,  # TODO add item.hint
                "check_name": (
                    f"{item.tool_id} ({item.title})" if item.title else item.tool_id
                ),
                "fingerprint": item.fingerprint,
                "severity": cls.severity_map[item.level],
                "location": {
                    "path": item.path,
                    "positions": {
                        "begin": {
                            "line": item.start_line or 1,
                        },
                    },
                },
            }
            if item.end_line:
                anno_item["location"]["positions"]["end"] = {}
                anno_item["location"]["positions"]["end"]["line"] = item.end_line
            if item.start_col:
                anno_item["location"]["positions"]["begin"]["column"] = item.start_col
            if item.end_col:
                anno_item["location"]["positions"]["end"]["column"] = item.end_col
            gl_annotations.append(anno_item)
        json.dump(gl_annotations, outfile, indent=2)


def main() -> None:
    argparser = argparse.ArgumentParser(description="Conversion from program output to CI/CD annotation formats")
    _ = argparser.add_argument(
        "informat",
        choices=InputAdapter.registry.keys(),
        metavar="INPUT_FORMAT",
        help="Choose from: " + ", ".join(InputAdapter.registry.keys()),
    )
    _ = argparser.add_argument(
        "outformat",
        choices=OutputAdapter.registry.keys(),
        metavar="OUTPUT_FORMAT",
        help="Choose from: " + ", ".join(OutputAdapter.registry.keys()),
    )
    _ = argparser.add_argument(
        "-i",
        metavar="INFILE",
        help="Input file (standard input if omitted)",
    )
    _ = argparser.add_argument(
        "-o",
        metavar="OUTFILE",
        help="Output file (standard output if omitted)",
    )
    args = argparser.parse_args()

    if args.i is None:
        cm = contextlib.nullcontext(sys.stdin)
    else:
        cm = open(args.i, "r", encoding="utf-8")

    with cm as infile:
        annotations = getattr(InputAdapter.registry[args.informat], "from_file")(infile)

    if args.o is None:
        cm = contextlib.nullcontext(sys.stdout)
    else:
        cm = open(args.o, "w", encoding="utf-8")

    with cm as outfile:
        getattr(OutputAdapter.registry[args.outformat], "to_file")(annotations, outfile)


if __name__ == "__main__":
    main()
