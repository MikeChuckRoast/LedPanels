# LED Panels Testing Guide

## Overview

This directory contains comprehensive unit and integration tests for the LED Panels display system.

## Test Structure

```
tests/
├── conftest.py                    # Shared pytest fixtures
├── fixtures/                      # Test data files
│   ├── sample_lynx.evt           # Sample event data
│   ├── sample_colors.csv         # Sample color mappings
│   ├── sample_settings.toml      # Sample configuration
│   └── sample_schedule.sch       # Sample schedule
├── test_config_loader.py         # Configuration loading tests
├── test_event_parser.py          # Event parsing tests
├── test_schedule_parser.py       # Schedule parsing tests
├── test_file_watcher.py          # File monitoring tests
├── test_matrix_backend.py        # Backend selection tests
├── test_fpp_output.py            # FPP protocol tests
├── test_colorlight_output.py     # ColorLight protocol tests
├── test_web_server.py            # Web interface tests
└── test_display_event.py         # Integration tests
```

## Running Tests

### Install Dependencies

```bash
pip install -r requirements-dev.txt
```

### Run All Tests

```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/test_config_loader.py
```

### Run with Coverage

```bash
pytest --cov=. --cov-report=html
```

Coverage report will be in `htmlcov/index.html`

### Run with Verbose Output

```bash
pytest -v
```

### Run Specific Test

```bash
pytest tests/test_config_loader.py::TestLoadSettings::test_loads_valid_settings_toml
```

## Test Categories

### Core Module Tests

- **test_config_loader.py**: Configuration file loading, validation, error handling
- **test_event_parser.py**: Lynx.evt parsing, color loading, athlete formatting
- **test_schedule_parser.py**: Schedule parsing, validation, navigation
- **test_file_watcher.py**: File monitoring, debouncing, callbacks

### Backend Tests

- **test_matrix_backend.py**: Backend selection logic, priority handling
- **test_fpp_output.py**: FPP/DDP protocol, network output, graphics
- **test_colorlight_output.py**: ColorLight protocol, Ethernet frames, BDF fonts

### Web and Integration Tests

- **test_web_server.py**: Flask routes, API endpoints, file operations
- **test_display_event.py**: Full application integration, navigation, rendering

## Writing New Tests

### Use Fixtures

Leverage shared fixtures from `conftest.py`:

```python
def test_my_feature(temp_config_dir, sample_settings_dict):
    # temp_config_dir provides isolated config directory
    # sample_settings_dict provides valid settings
    pass
```

### Parametrize Tests

Use `@pytest.mark.parametrize` for multiple test cases:

```python
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
])
def test_multiply_by_two(input, expected):
    assert input * 2 == expected
```

### Mock External Dependencies

Mock hardware, network, and file system operations:

```python
@patch('socket.socket')
def test_network_operation(mock_socket):
    # Test without real network calls
    pass
```

## Continuous Integration

Tests can be run in CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: |
    pip install -r requirements-dev.txt
    pytest --cov=. --cov-report=xml
```

## Tips

- **Isolation**: Each test should be independent and not affect others
- **Mocking**: Mock external dependencies (hardware, network, files)
- **Fixtures**: Use fixtures for common setup/teardown
- **Coverage**: Aim for >80% code coverage
- **Speed**: Keep tests fast; use mocks instead of real I/O

## Troubleshooting

### Import Errors

If you see import errors, ensure the parent directory is in the Python path:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### File Watcher Tests Timing Out

File watcher tests may be slower due to debouncing. Adjust timeouts if needed:

```python
@pytest.mark.timeout(10)
def test_file_watcher():
    pass
```

### Mock Not Working

Ensure you're mocking at the correct import location:

```python
# Mock where it's used, not where it's defined
@patch('module_using_it.socket.socket')  # Correct
# not @patch('socket.socket')  # May not work
```
