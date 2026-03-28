"""Sandbox for executing untrusted attacker genome code — Section 13.1 of the spec."""

from __future__ import annotations

import ast
import logging
import signal
import textwrap
from typing import Any

logger = logging.getLogger(__name__)

BLOCKED_IMPORTS = frozenset({
    "os", "sys", "subprocess", "shutil", "socket",
    "http", "urllib", "requests", "pathlib", "importlib",
    "ctypes", "multiprocessing", "signal", "io",
    "pickle", "shelve", "tempfile", "glob",
    "code", "codeop", "compileall", "py_compile",
    "webbrowser", "antigravity",
})

BLOCKED_BUILTINS = frozenset({
    "exec", "eval", "compile", "__import__",
    "open", "input", "breakpoint",
    "exit", "quit",
})

ALLOWED_IMPORTS = frozenset({
    "random", "string", "re", "math", "collections",
    "itertools", "functools", "hashlib", "json",
    "textwrap", "copy", "enum", "dataclasses",
    "typing", "abc", "operator",
    "base64", "binascii", "codecs",
})


def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    """Import gate that only allows modules from ALLOWED_IMPORTS."""
    root = name.split(".")[0]
    if root not in ALLOWED_IMPORTS:
        raise ImportError(f"Import of '{name}' is not allowed in the sandbox")
    return __builtins__["__import__"](name, globals, locals, fromlist, level) if isinstance(__builtins__, dict) else __import__(name, globals, locals, fromlist, level)

_SAFE_BUILTINS = {
    "__build_class__": __builtins__["__build_class__"] if isinstance(__builtins__, dict) else getattr(__builtins__, "__build_class__"),
    "__import__": _restricted_import,
    "True": True,
    "False": False,
    "None": None,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "chr": chr,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "getattr": getattr,
    "hasattr": hasattr,
    "hash": hash,
    "hex": hex,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "object": object,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "print": lambda *a, **kw: None,  # silenced
    "property": property,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "staticmethod": staticmethod,
    "str": str,
    "sum": sum,
    "super": super,
    "tuple": tuple,
    "type": type,
    "zip": zip,
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "AttributeError": AttributeError,
    "RuntimeError": RuntimeError,
    "StopIteration": StopIteration,
    "NotImplementedError": NotImplementedError,
}


class SandboxError(Exception):
    pass


class SandboxTimeout(SandboxError):
    pass


class AttackerSandbox:
    """Execute attacker genomes in a restricted environment.

    - No filesystem access
    - No network access
    - No dangerous builtins
    - Execution timeout (default 5s per call)
    """

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    def validate_code(self, code: str) -> list[str]:
        """Static analysis to catch obvious escape attempts. Returns list of violations."""
        violations = []
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [f"Syntax error: {e}"]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_root = alias.name.split(".")[0]
                    if module_root in BLOCKED_IMPORTS:
                        violations.append(f"Blocked import: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_root = node.module.split(".")[0]
                    if module_root in BLOCKED_IMPORTS:
                        violations.append(f"Blocked import from: {node.module}")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_BUILTINS:
                    violations.append(f"Blocked builtin call: {node.func.id}")
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr in ("system", "popen", "exec", "spawn"):
                        violations.append(f"Blocked method call: {node.func.attr}")
        return violations

    def instantiate_attacker(self, code: str) -> Any:
        """Compile and instantiate the AttackStrategy class from code."""
        violations = self.validate_code(code)
        if violations:
            raise SandboxError(f"Code validation failed: {'; '.join(violations)}")

        namespace: dict[str, Any] = {
            "__builtins__": dict(_SAFE_BUILTINS),
            "__name__": "<attacker_sandbox>",
        }
        try:
            compiled = compile(code, "<attacker_sandbox>", "exec")
            exec(compiled, namespace)  # noqa: S102 — intentional sandboxed exec
        except Exception as e:
            raise SandboxError(f"Code execution failed: {e}") from e

        attack_cls = namespace.get("AttackStrategy")
        if attack_cls is None:
            raise SandboxError("Code does not define an AttackStrategy class")

        try:
            instance = attack_cls()
        except Exception as e:
            raise SandboxError(f"AttackStrategy instantiation failed: {e}") from e

        for method in ("generate_attack", "get_target_address", "get_requested_amount"):
            if not callable(getattr(instance, method, None)):
                raise SandboxError(f"AttackStrategy missing required method: {method}")

        return instance

    def execute_attack_turn(
        self,
        attacker_code: str,
        turn_number: int,
        conversation_history: list[dict],
        timeout: float | None = None,
    ) -> str:
        """Execute the attacker's generate_attack method and return the message."""
        timeout = timeout or self.timeout
        instance = self.instantiate_attacker(attacker_code)

        def _handler(signum: int, frame: Any) -> None:
            raise SandboxTimeout(f"Attacker code execution timed out after {timeout}s")

        old_handler = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(int(timeout))
        try:
            result = instance.generate_attack(turn_number, list(conversation_history))
            if not isinstance(result, str):
                raise SandboxError(f"generate_attack must return str, got {type(result).__name__}")
            return result
        except SandboxTimeout:
            raise
        except Exception as e:
            raise SandboxError(f"generate_attack raised: {e}") from e
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

    def get_target_address(self, attacker_code: str) -> str:
        instance = self.instantiate_attacker(attacker_code)
        result = instance.get_target_address()
        if not isinstance(result, str):
            raise SandboxError(f"get_target_address must return str, got {type(result).__name__}")
        return result

    def get_requested_amount(self, attacker_code: str) -> float:
        instance = self.instantiate_attacker(attacker_code)
        result = instance.get_requested_amount()
        if not isinstance(result, (int, float)):
            raise SandboxError(f"get_requested_amount must return float, got {type(result).__name__}")
        return float(result)
