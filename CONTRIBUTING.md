# Contributing to django-payments-tr

Thank you for your interest in contributing to django-payments-tr! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/) package manager (recommended) or pip

### Setting Up the Development Environment

1. **Clone the repository**

   ```bash
   git clone https://github.com/aladagemre/django-payments-tr
   cd django-payments-tr
   ```

2. **Create a virtual environment and install dependencies**

   Using uv (recommended):
   ```bash
   uv venv
   uv pip install -e ".[dev,all]"
   ```

   Using pip:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e ".[dev,all]"
   ```

3. **Verify your setup**

   ```bash
   pytest
   ruff check .
   mypy src
   ```

## Development Workflow

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/payments_tr --cov-report=html

# Run specific test file
pytest tests/test_kdv.py

# Run tests matching a pattern
pytest -k "test_validate"

# Stop on first failure
pytest -x
```

### Code Quality

We use several tools to maintain code quality:

```bash
# Linting with ruff
ruff check .

# Auto-fix lint issues
ruff check --fix .

# Format code
ruff format .

# Type checking with mypy
mypy src
```

### Pre-commit Checks

Before submitting a PR, ensure all checks pass:

```bash
pytest
ruff check .
mypy src
```

## Submitting Changes

### Pull Request Process

1. **Fork the repository** and create a new branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the coding standards below.

3. **Add tests** for any new functionality.

4. **Update documentation** if needed (README.md, docstrings).

5. **Run all checks** to ensure nothing is broken:
   ```bash
   pytest
   ruff check .
   mypy src
   ```

6. **Commit your changes** with a clear, descriptive message:
   ```bash
   git commit -m "Add feature: description of what you added"
   ```

7. **Push to your fork** and create a Pull Request.

### Commit Message Guidelines

- Use the present tense ("Add feature" not "Added feature")
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Keep the first line under 72 characters
- Reference issues and PRs where appropriate

Examples:
- `Add VKN validation function`
- `Fix IBAN validation for edge cases`
- `Update KDV rates for 2025`
- `Refactor provider registry for better extensibility`

## Coding Standards

### Python Style

- Follow [PEP 8](https://peps.python.org/pep-0008/) style guidelines
- Use type hints for all function signatures
- Maximum line length: 100 characters
- Use double quotes for strings (enforced by ruff)

### Code Organization

```
src/payments_tr/
├── __init__.py          # Public API exports
├── apps.py              # Django app config
├── contrib/             # Optional integrations (DRF serializers)
├── eft/                 # EFT payment workflow
├── providers/           # Payment provider implementations
├── tax/                 # Tax calculations (KDV)
└── validation/          # Turkish-specific validators
```

### Testing Guidelines

- Write tests for all new functionality
- Place tests in the `tests/` directory
- Use descriptive test names: `test_validate_tckn_with_valid_number`
- Test edge cases and error conditions
- Aim for high coverage but prioritize meaningful tests

### Documentation

- Add docstrings to all public functions and classes
- Use Google-style docstrings
- Update README.md for user-facing changes
- Update CHANGELOG.md following [Keep a Changelog](https://keepachangelog.com/) format

## Adding a New Payment Provider

To add a new payment provider:

1. Create a new file in `src/payments_tr/providers/`:
   ```python
   # src/payments_tr/providers/paytr.py
   from .base import PaymentProvider, PaymentResult

   class PayTRProvider(PaymentProvider):
       provider_name = "paytr"

       def create_payment(self, payment, **kwargs):
           # Implementation
           pass

       # Implement all abstract methods
   ```

2. Register the provider in `src/payments_tr/providers/__init__.py`:
   ```python
   from .paytr import PayTRProvider
   register_provider("paytr", PayTRProvider)
   ```

3. Add tests in `tests/test_paytr_provider.py`

4. Update documentation in README.md

## Reporting Issues

### Bug Reports

When reporting bugs, please include:

- Python version
- Django version
- django-payments-tr version
- Steps to reproduce
- Expected vs actual behavior
- Error messages/tracebacks

### Feature Requests

For feature requests, please describe:

- The use case
- Expected behavior
- Any alternative solutions you've considered

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow

## Questions?

If you have questions, feel free to:

- Open an issue on GitHub
- Check existing issues for similar questions

Thank you for contributing!
