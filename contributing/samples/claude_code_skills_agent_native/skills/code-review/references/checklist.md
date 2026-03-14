# Code Review Checklist

## Security
- [ ] No hardcoded secrets or credentials
- [ ] Inputs are validated at system boundaries
- [ ] No command injection, path traversal, or arbitrary file writes

## Quality
- [ ] No dead code or unused imports
- [ ] Functions have a single responsibility
- [ ] No functions longer than 50 lines without clear justification

## Style
- [ ] Consistent naming conventions
- [ ] No magic numbers when a named constant would improve clarity
- [ ] Error handling is explicit, not silent
