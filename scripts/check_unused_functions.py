#!/usr/bin/env python3
"""
Check for unused functions, classes, and constants in the project.

This script scans all Python files in the Django apps,
identifies function/class/constant definitions, and reports any
that are not referenced elsewhere in the codebase.

Usage:
    python scripts/check_unused_functions.py
    # or
    make unused
"""
# ruff: noqa: T201

import ast
import sys
from collections import defaultdict
from pathlib import Path

# Django apps and core directories to scan
DJANGO_APPS = [
    "apps/core",
    "apps/orders",
    "config",
]

# Functions that are expected to be unused (entry points, callbacks, etc.)
IGNORED_FUNCTIONS = {
    # Django management commands
    "handle",
    "add_arguments",
    # Django signals
    "ready",
    # Celery tasks (called dynamically)
    "debug_task",
    # Celery bootstep hooks
    "start",
    "stop",
    # Test functions
    "test_",
    # Pydantic validators (field_validator, model_validator)
    "validate_",
    # Django model methods
    "save",
    "delete",
    "clean",
    "get_absolute_url",
    # Django middleware methods
    "process_request",
    "process_response",
    "process_view",
    "process_exception",
    "process_template_response",
    # Django admin override methods
    "get_queryset",
    "get_readonly_fields",
    "get_fieldsets",
    "get_list_display",
    "get_list_filter",
    "get_search_fields",
    "get_ordering",
    "has_add_permission",
    "has_change_permission",
    "has_delete_permission",
    "has_view_permission",
    "save_model",
    "delete_model",
    # Magic methods
    "__init__",
    "__str__",
    "__repr__",
    "__call__",
    "__enter__",
    "__exit__",
    "__aenter__",
    "__aexit__",
    "__hash__",
    "__eq__",
}

# Classes that are expected to be unused (base classes, mixins, etc.)
IGNORED_CLASSES = {
    # Django base classes
    "Meta",
    # Django management command (dynamically loaded by Django)
    "Command",
    # Django admin classes (registered via decorator or admin.site.register)
    "Admin",
    "ModelAdmin",
    "TabularInline",
    "StackedInline",
    # Exception classes (raised, not called)
    "Error",
    "Exception",
    # Pydantic config classes
    "Config",
    "ConfigDict",
    # Test classes
    "Test",
}

# Variables/constants that are expected to be unused or used dynamically
IGNORED_VARIABLES = {
    # Django standard settings
    "DEBUG",
    "SECRET_KEY",
    "ALLOWED_HOSTS",
    "INSTALLED_APPS",
    "MIDDLEWARE",
    "ROOT_URLCONF",
    "TEMPLATES",
    "WSGI_APPLICATION",
    "ASGI_APPLICATION",
    "DATABASES",
    "AUTH_PASSWORD_VALIDATORS",
    "LANGUAGE_CODE",
    "TIME_ZONE",
    "USE_I18N",
    "USE_TZ",
    "STATIC_URL",
    "STATIC_ROOT",
    "DEFAULT_AUTO_FIELD",
    "CACHES",
    "BASE_DIR",
    "CORS_ALLOWED_ORIGINS",
    "CORS_ALLOW_CREDENTIALS",
    # Security settings
    "SECURE_BROWSER_XSS_FILTER",
    "SECURE_CONTENT_TYPE_NOSNIFF",
    "X_FRAME_OPTIONS",
    "SECURE_PROXY_SSL_HEADER",
    "SECURE_SSL_REDIRECT",
    "SECURE_HSTS_SECONDS",
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    "SECURE_HSTS_PRELOAD",
    "SESSION_COOKIE_SECURE",
    "SESSION_COOKIE_HTTPONLY",
    "CSRF_COOKIE_SECURE",
    # Celery settings
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "CELERY_ACCEPT_CONTENT",
    "CELERY_TASK_SERIALIZER",
    "CELERY_RESULT_SERIALIZER",
    "CELERY_TIMEZONE",
    "CELERY_TASK_TRACK_STARTED",
    "CELERY_TASK_ACKS_LATE",
    "CELERY_TASK_TIME_LIMIT",
    "CELERY_TASK_SOFT_TIME_LIMIT",
    # Slack settings
    "SLACK_ENABLED",
    "SLACK_BOT_TOKEN",
    "SLACK_CHANNEL",
    # App-specific config loaded dynamically
    "app_name",
    "default_app_config",
    "urlpatterns",
    "api",
    "celery_app",
    # Pydantic model config
    "model_config",
}

# Decorators that indicate the function is used externally (not direct calls)
EXTERNAL_USE_DECORATORS = {
    # Django Ninja route decorators
    "get",
    "post",
    "put",
    "delete",
    "patch",
    "options",
    "head",
    "api_operation",
    # Celery task decorator
    "task",
    "shared_task",
    # Celery/Django signal decorators
    "connect",
    # Context managers
    "contextmanager",
    "asynccontextmanager",
    # Django decorators
    "receiver",
    "property",
    "staticmethod",
    "classmethod",
    # Django admin actions and display
    "action",
    "display",
    "register",
    # Pydantic validators
    "field_validator",
    "model_validator",
    "validator",
    "root_validator",
    # Pytest fixtures
    "fixture",
    "pytest.fixture",
    # Django Ninja exception handlers
    "exception_handler",
}

# Directories to skip
SKIP_DIRS = {"__pycache__", ".venv", "venv", ".git", "node_modules", "migrations"}

# Files to skip for definition extraction (Django models are used dynamically by ORM)
# Note: We still collect references FROM these files, just don't check if definitions IN them are unused
SKIP_FILES_FOR_DEFINITIONS = {"models.py"}


def get_python_files(
    root_dir: Path, apps: list[str], skip_files: set[str] | None = None
) -> list[Path]:
    """Get all Python files in the Django apps, excluding test files and migrations.

    Args:
        root_dir: Project root directory
        apps: List of app directories to scan
        skip_files: Optional set of filenames to skip (e.g., {"models.py"})
    """
    if skip_files is None:
        skip_files = set()

    python_files = []
    for app in apps:
        app_dir = root_dir / app
        if not app_dir.exists():
            continue
        for path in app_dir.rglob("*.py"):
            # Skip directories
            if any(skip_dir in path.parts for skip_dir in SKIP_DIRS):
                continue
            # Skip specific files if specified
            if path.name in skip_files:
                continue
            # Skip test files
            if path.name.startswith("test_") or path.name.endswith("_test.py"):
                continue
            python_files.append(path)
    return python_files


def has_external_use_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if function has a decorator indicating external use."""
    for decorator in node.decorator_list:
        # Handle @router.get, @app.post, @api.exception_handler, etc.
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                if decorator.func.attr in EXTERNAL_USE_DECORATORS:
                    return True
            elif isinstance(decorator.func, ast.Name):
                if decorator.func.id in EXTERNAL_USE_DECORATORS:
                    return True
        # Handle @contextmanager (without call)
        elif isinstance(decorator, ast.Attribute):
            if decorator.attr in EXTERNAL_USE_DECORATORS:
                return True
        elif isinstance(decorator, ast.Name):
            if decorator.id in EXTERNAL_USE_DECORATORS:
                return True
    return False


def extract_function_definitions(file_path: Path) -> dict[str, int]:
    """Extract all function definitions from a Python file."""
    functions = {}
    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                # Skip private functions (starting with _)
                if node.name.startswith("_"):
                    continue
                # Skip ignored functions
                if any(
                    node.name == ignored or node.name.startswith(ignored)
                    for ignored in IGNORED_FUNCTIONS
                ):
                    continue
                # Skip functions with external use decorators (Django Ninja routes, Celery tasks)
                if has_external_use_decorator(node):
                    continue
                functions[node.name] = node.lineno
    except SyntaxError:
        pass

    return functions


def has_external_use_class_decorator(node: ast.ClassDef) -> bool:
    """Check if class has a decorator indicating external use."""
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                if decorator.func.attr in {"register"}:
                    return True
            elif isinstance(decorator.func, ast.Name):
                if decorator.func.id in {"dataclass", "total_ordering"}:
                    return True
        elif isinstance(decorator, ast.Attribute):
            if decorator.attr in {"register"}:
                return True
        elif isinstance(decorator, ast.Name):
            if decorator.id in {"dataclass", "total_ordering"}:
                return True
    return False


def extract_class_definitions(file_path: Path) -> dict[str, int]:
    """Extract all class definitions from a Python file."""
    classes = {}
    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Skip private classes (starting with _)
                if node.name.startswith("_"):
                    continue
                # Skip ignored classes
                if any(
                    node.name == ignored or node.name.endswith(ignored)
                    for ignored in IGNORED_CLASSES
                ):
                    continue
                # Skip classes with external use decorators
                if has_external_use_class_decorator(node):
                    continue
                classes[node.name] = node.lineno
    except SyntaxError:
        pass

    return classes


def extract_variable_definitions(file_path: Path) -> dict[str, int]:
    """Extract module-level constant/variable definitions from a Python file.

    Only extracts:
    - UPPER_CASE constants (like PROMPT, API_KEY, etc.)
    - Variables with type annotations at module level
    """
    variables = {}
    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        # Only look at top-level statements (module level)
        for node in tree.body:
            # Handle simple assignments: PROMPT = "..."
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id
                        # Only track UPPER_CASE constants
                        if name.isupper() or (
                            "_" in name and name.replace("_", "").isupper()
                        ):
                            if name.startswith("_"):
                                continue
                            if name in IGNORED_VARIABLES:
                                continue
                            variables[name] = node.lineno

            # Handle annotated assignments: PROMPT: str = "..."
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
                # Only track UPPER_CASE constants
                if name.isupper() or ("_" in name and name.replace("_", "").isupper()):
                    if name.startswith("_"):
                        continue
                    if name in IGNORED_VARIABLES:
                        continue
                    variables[name] = node.lineno

    except SyntaxError:
        pass

    return variables


def extract_references(file_path: Path) -> set[str]:
    """Extract all name references from a Python file."""
    references = set()
    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))

        for node in ast.walk(tree):
            # Function calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    references.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    references.add(node.func.attr)

            # Name references (variables, imports)
            elif isinstance(node, ast.Name):
                references.add(node.id)

            # Attribute access
            elif isinstance(node, ast.Attribute):
                references.add(node.attr)

            # Import statements
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    references.add(name.split(".")[0])

            # From imports
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    references.add(name)

            # String constants (for Django admin list_display, settings, etc.)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value
                # Handle dotted paths (extract last part)
                if "." in value:
                    last_part = value.rsplit(".", 1)[-1]
                    if last_part.isidentifier():
                        references.add(last_part)
                # Simple identifier
                elif value.isidentifier():
                    references.add(value)

    except SyntaxError:
        pass

    return references


def find_unused_symbols(
    root_dir: Path, apps: list[str]
) -> tuple[
    dict[Path, list[tuple[str, int]]],  # functions
    dict[Path, list[tuple[str, int]]],  # classes
    dict[Path, list[tuple[str, int]]],  # variables
]:
    """Find all unused functions, classes, and constants in the project."""
    # Files for definition extraction (skip models.py - Django ORM uses them dynamically)
    definition_files = get_python_files(
        root_dir, apps, skip_files=SKIP_FILES_FOR_DEFINITIONS
    )
    # Files for reference collection (include ALL files to find all usages)
    all_files = get_python_files(root_dir, apps, skip_files=None)

    # Also collect references from tests directory
    tests_dir = root_dir / "tests"
    if tests_dir.exists():
        for path in tests_dir.rglob("*.py"):
            if any(skip_dir in path.parts for skip_dir in SKIP_DIRS):
                continue
            all_files.append(path)

    # Collect all definitions (only from non-skipped files)
    all_func_definitions: dict[Path, dict[str, int]] = {}
    all_class_definitions: dict[Path, dict[str, int]] = {}
    all_var_definitions: dict[Path, dict[str, int]] = {}

    for file_path in definition_files:
        func_defs = extract_function_definitions(file_path)
        if func_defs:
            all_func_definitions[file_path] = func_defs

        class_defs = extract_class_definitions(file_path)
        if class_defs:
            all_class_definitions[file_path] = class_defs

        var_defs = extract_variable_definitions(file_path)
        if var_defs:
            all_var_definitions[file_path] = var_defs

    # Collect all references from ALL files (including models.py and tests)
    all_references: set[str] = set()
    for file_path in all_files:
        references = extract_references(file_path)
        all_references.update(references)

    # Find unused symbols
    unused_funcs: dict[Path, list[tuple[str, int]]] = defaultdict(list)
    for file_path, definitions in all_func_definitions.items():
        for name, line_no in definitions.items():
            if name not in all_references:
                unused_funcs[file_path].append((name, line_no))

    unused_classes: dict[Path, list[tuple[str, int]]] = defaultdict(list)
    for file_path, definitions in all_class_definitions.items():
        for name, line_no in definitions.items():
            if name not in all_references:
                unused_classes[file_path].append((name, line_no))

    unused_vars: dict[Path, list[tuple[str, int]]] = defaultdict(list)
    for file_path, definitions in all_var_definitions.items():
        for name, line_no in definitions.items():
            if name not in all_references:
                unused_vars[file_path].append((name, line_no))

    return dict(unused_funcs), dict(unused_classes), dict(unused_vars)


def print_unused_items(
    items: dict[Path, list[tuple[str, int]]],
    project_root: Path,
    symbol_type: str,
    suffix: str,
) -> int:
    """Print unused items and return count."""
    count = 0
    for file_path, symbols in sorted(items.items()):
        rel_path = file_path.relative_to(project_root)
        for name, line_no in sorted(symbols, key=lambda x: x[1]):
            print(f"  {rel_path}:{line_no} - {name}{suffix}")
            count += 1
    return count


def main() -> None:
    """Main entry point."""
    # Find project root (where Django apps are)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # Verify at least one app exists
    existing_apps = [app for app in DJANGO_APPS if (project_root / app).exists()]
    if not existing_apps:
        print(f"Error: No Django apps found at {project_root}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning for unused symbols in: {project_root}")
    print(f"Apps: {', '.join(existing_apps)}\n")

    unused_funcs, unused_classes, unused_vars = find_unused_symbols(
        project_root, existing_apps
    )

    total_unused = 0

    # Print unused functions
    if unused_funcs:
        print("=" * 60)
        print("UNUSED FUNCTIONS")
        print("=" * 60)
        total_unused += print_unused_items(unused_funcs, project_root, "function", "()")
        print()

    # Print unused classes
    if unused_classes:
        print("=" * 60)
        print("UNUSED CLASSES")
        print("=" * 60)
        total_unused += print_unused_items(unused_classes, project_root, "class", "")
        print()

    # Print unused constants/variables
    if unused_vars:
        print("=" * 60)
        print("UNUSED CONSTANTS")
        print("=" * 60)
        total_unused += print_unused_items(unused_vars, project_root, "constant", "")
        print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    func_count = sum(len(items) for items in unused_funcs.values())
    class_count = sum(len(items) for items in unused_classes.values())
    var_count = sum(len(items) for items in unused_vars.values())
    print(f"  Unused functions: {func_count}")
    print(f"  Unused classes:   {class_count}")
    print(f"  Unused constants: {var_count}")
    print(f"  Total:            {total_unused}")

    if total_unused == 0:
        print("\nNo unused symbols found!")

    sys.exit(1 if total_unused > 0 else 0)


if __name__ == "__main__":
    main()
