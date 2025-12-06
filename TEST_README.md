# Unit Tests for LED Panels Display Event

## Overview

The `test_display_event.py` file contains comprehensive unit tests for the `display_event.py` module. The tests cover all major functionality including parsing, formatting, lane filling, color handling, pagination, and heat navigation.

## Running the Tests

### Using Python's unittest module (recommended)

```bash
python -m unittest test_display_event -v
```

The `-v` flag provides verbose output showing each test as it runs.

### Running specific test classes

To run tests for a specific feature:

```bash
# Test only parsing functionality
python -m unittest test_display_event.TestParseLynxFile -v

# Test only lane filling logic
python -m unittest test_display_event.TestLaneFilling -v

# Test only color parsing
python -m unittest test_display_event.TestColorParsing -v
```

### Running individual tests

```bash
python -m unittest test_display_event.TestParseLynxFile.test_parse_individual_event -v
```

## Test Coverage

### 1. Lynx File Parsing (`TestParseLynxFile`)
- ✅ Parse individual events with athletes
- ✅ Parse relay events
- ✅ Parse multiple heats of the same event
- ✅ Handle missing files
- ✅ Ignore empty lines

### 2. Relay Event Detection (`TestRelayDetection`)
- ✅ Detect relay events correctly
- ✅ Distinguish from individual events
- ✅ Handle empty athlete lists
- ✅ Extract relay suffix letters (A, B, C)

### 3. Athlete Formatting (`TestAthleteFormatting`)
- ✅ Format individual athlete names ("First L.")
- ✅ Format relay team names ("Team A")
- ✅ Handle missing names
- ✅ Handle missing fields gracefully

### 4. Lane Filling (`TestLaneFilling`)
- ✅ Fill consecutive lanes correctly
- ✅ Fill lanes with gaps (e.g., lanes 2, 3, 5 → show 1-5 with 1 and 4 empty)
- ✅ Handle lanes starting at non-1 values
- ✅ Handle empty athlete lists
- ✅ Ignore non-numeric lane values

### 5. Color Parsing (`TestColorParsing`)
- ✅ Load valid color files
- ✅ Parse hex colors with and without # prefix
- ✅ Handle missing files gracefully
- ✅ Validate hex color format
- ✅ Handle invalid colors

### 6. Pagination (`TestPagination`)
- ✅ Single page scenarios
- ✅ Multiple page scenarios
- ✅ Empty lists
- ✅ Exact fit scenarios

### 7. Heat Navigation (`TestHeatNavigation`)
- ✅ Navigate to next heat when it exists
- ✅ Stay on current heat when next doesn't exist
- ✅ Navigate to previous heat when it exists
- ✅ Prevent going below heat 1
- ✅ Reset to original heat

## Test Results

All 32 tests pass successfully:

```
Ran 32 tests in 0.064s

OK
```

## Code Refactoring for Testability

The following functions were extracted or created to improve testability:

1. **`parse_hex_color(hex_str)`** - Extracted color parsing logic
2. **`fill_lanes_with_empty_rows(athletes)`** - Extracted lane filling logic
3. All parsing and formatting functions were already well-structured as pure functions

## Dependencies

The tests use only Python's standard library:
- `unittest` - Test framework
- `tempfile` - For creating temporary test files
- `os` - For file operations
- `unittest.mock` - For mocking (if needed in future tests)

No additional packages are required to run the tests.

## Adding New Tests

When adding new features, follow this pattern:

```python
class TestNewFeature(unittest.TestCase):
    """Test description."""
    
    def test_specific_behavior(self):
        """Test specific behavior description."""
        # Arrange
        input_data = {...}
        
        # Act
        result = function_to_test(input_data)
        
        # Assert
        self.assertEqual(result, expected_value)
```

## Continuous Integration

These tests can be easily integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: python -m unittest test_display_event -v
```

## Notes

- Tests use temporary files for file I/O operations and clean up automatically
- All tests are independent and can run in any order
- No external services or hardware required
- Tests run in under 100ms total
