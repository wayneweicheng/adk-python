# Code Review Checklist

## Security
- [ ] No hardcoded secrets or credentials
- [ ] Inputs are validated at system boundaries
- [ ] No SQL / command injection vectors

## Quality
- [ ] No dead code or unused imports
- [ ] Functions have a single responsibility
- [ ] No functions longer than 50 lines

## Style
- [ ] Consistent naming conventions
- [ ] No magic numbers (use named constants)
- [ ] Error handling is explicit, not silent
