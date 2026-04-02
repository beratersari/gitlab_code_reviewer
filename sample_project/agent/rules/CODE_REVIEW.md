# Code Review Guidelines

## Python Standards

### Type Hints
- All function parameters must have type hints
- Return types must be explicitly declared
- Use `Optional[T]` instead of `Union[T, None]`

### Naming Conventions
- Functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

### Error Handling
- Never use bare `except:` clauses
- Always catch specific exceptions
- Use custom exception classes for domain errors
- Log exceptions with context before re-raising

### Performance
- Avoid nested loops where possible (O(n²) complexity)
- Use list/dict comprehensions for simple transformations
- Cache expensive computations with `@functools.lru_cache`

### Security
- Validate all user inputs
- Use parameterized queries for database operations
- Never log sensitive data (passwords, tokens, PII)
- Check for SQL injection vulnerabilities in raw queries

## Code Quality

### Documentation
- All public functions must have docstrings
- Use Google-style docstrings
- Include examples in docstrings for complex functions

### Testing
- Unit tests required for all business logic
- Maintain minimum 80% code coverage
- Use pytest fixtures for test setup

### Git
- Commit messages should be descriptive
- Keep functions under 50 lines when possible
- One logical change per commit
