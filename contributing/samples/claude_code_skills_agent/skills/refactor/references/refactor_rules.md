# Refactoring Rules

## Always apply
- Remove unused imports
- Replace magic numbers with named constants
- Split functions longer than 50 lines into smaller ones
- Use list/dict comprehensions instead of manual loops where readable
- Add explicit error handling at system boundaries (file I/O, network)

## Python-specific
- Use `pathlib.Path` instead of `os.path` string manipulation
- Prefer f-strings over `.format()` or `%` formatting
- Use `with` statements for all file/resource handling
- Replace bare `except:` with specific exception types

## Do NOT change
- Public API signatures (function names, arguments) unless clearly broken
- Business logic — only structure and style
- Working tests
