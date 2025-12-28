"""Tests for retry utilities."""

from unittest.mock import patch

import pytest

from payments_tr.retry import (
    RetryableOperation,
    RetryAttempt,
    RetryConfig,
    async_retry_with_backoff,
    retry_with_backoff,
)


class TestRetryConfig:
    """Test RetryConfig class."""

    def test_init_defaults(self):
        """Test initialization with defaults."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True

    def test_init_custom(self):
        """Test initialization with custom values."""
        config = RetryConfig(
            max_attempts=5,
            initial_delay=0.5,
            max_delay=30.0,
            exponential_base=3.0,
            jitter=False,
        )
        assert config.max_attempts == 5
        assert config.initial_delay == 0.5
        assert config.max_delay == 30.0
        assert config.exponential_base == 3.0
        assert config.jitter is False

    def test_get_delay_first_attempt(self):
        """Test delay calculation for first attempt."""
        config = RetryConfig(initial_delay=1.0, exponential_base=2.0, jitter=False)
        delay = config.get_delay(0)
        assert delay == 1.0

    def test_get_delay_exponential(self):
        """Test exponential delay calculation."""
        config = RetryConfig(initial_delay=1.0, exponential_base=2.0, jitter=False)
        assert config.get_delay(0) == 1.0  # 1.0 * 2^0
        assert config.get_delay(1) == 2.0  # 1.0 * 2^1
        assert config.get_delay(2) == 4.0  # 1.0 * 2^2
        assert config.get_delay(3) == 8.0  # 1.0 * 2^3

    def test_get_delay_max_delay(self):
        """Test that delay doesn't exceed max_delay."""
        config = RetryConfig(initial_delay=1.0, max_delay=5.0, jitter=False)
        delay = config.get_delay(10)  # Would be 1024 without max
        assert delay == 5.0

    def test_get_delay_with_jitter(self):
        """Test delay with jitter adds randomness."""
        config = RetryConfig(initial_delay=2.0, exponential_base=2.0, jitter=True)

        # Run multiple times to check jitter variation
        delays = [config.get_delay(1) for _ in range(10)]

        # All delays should be between 50% and 150% of base delay (4.0)
        base_delay = 4.0
        for delay in delays:
            assert base_delay * 0.5 <= delay <= base_delay * 1.5

        # There should be some variation
        assert len(set(delays)) > 1

    def test_get_delay_without_jitter(self):
        """Test delay without jitter is deterministic."""
        config = RetryConfig(initial_delay=2.0, exponential_base=2.0, jitter=False)

        # Run multiple times - should always be the same
        delays = [config.get_delay(1) for _ in range(5)]
        assert all(d == 4.0 for d in delays)


class TestRetryWithBackoff:
    """Test retry_with_backoff decorator."""

    def test_success_first_attempt(self):
        """Test successful function on first attempt."""
        call_count = {"value": 0}

        @retry_with_backoff(max_attempts=3)
        def successful_function():
            call_count["value"] += 1
            return "success"

        result = successful_function()

        assert result == "success"
        assert call_count["value"] == 1

    def test_success_after_retries(self, caplog):
        """Test successful function after retries."""
        import logging

        caplog.set_level(logging.WARNING)
        call_count = {"value": 0}

        @retry_with_backoff(max_attempts=3, initial_delay=0.01)
        def flaky_function():
            call_count["value"] += 1
            if call_count["value"] < 2:
                raise ValueError("Temporary error")
            return "success"

        result = flaky_function()

        assert result == "success"
        assert call_count["value"] == 2
        assert "retrying" in caplog.text.lower()

    def test_all_attempts_fail(self, caplog):
        """Test function that fails all retry attempts."""
        import logging

        caplog.set_level(logging.ERROR)
        call_count = {"value": 0}

        @retry_with_backoff(max_attempts=3, initial_delay=0.01)
        def always_fails():
            call_count["value"] += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            always_fails()

        assert call_count["value"] == 3
        assert "failed after 3 attempts" in caplog.text.lower()

    def test_specific_exceptions_only(self):
        """Test that only specified exceptions are retried."""
        call_count = {"value": 0}

        @retry_with_backoff(max_attempts=3, exceptions=(ValueError,), initial_delay=0.01)
        def raises_type_error():
            call_count["value"] += 1
            raise TypeError("Not retried")

        with pytest.raises(TypeError, match="Not retried"):
            raises_type_error()

        # Should fail immediately, not retry
        assert call_count["value"] == 1

    def test_multiple_exception_types(self):
        """Test retrying multiple exception types."""
        call_count = {"value": 0}

        @retry_with_backoff(
            max_attempts=3,
            exceptions=(ValueError, TypeError),
            initial_delay=0.01,
        )
        def raises_different_errors():
            call_count["value"] += 1
            if call_count["value"] == 1:
                raise ValueError("First error")
            if call_count["value"] == 2:
                raise TypeError("Second error")
            return "success"

        result = raises_different_errors()

        assert result == "success"
        assert call_count["value"] == 3

    def test_on_retry_callback(self):
        """Test on_retry callback is called."""
        retry_info = {"count": 0, "exceptions": []}

        def on_retry_callback(exception, attempt):
            retry_info["count"] += 1
            retry_info["exceptions"].append((exception, attempt))

        call_count = {"value": 0}

        @retry_with_backoff(
            max_attempts=3,
            initial_delay=0.01,
            on_retry=on_retry_callback,
        )
        def flaky_function():
            call_count["value"] += 1
            if call_count["value"] < 3:
                raise ValueError(f"Error {call_count['value']}")
            return "success"

        result = flaky_function()

        assert result == "success"
        assert retry_info["count"] == 2
        assert len(retry_info["exceptions"]) == 2
        assert retry_info["exceptions"][0][1] == 0  # First attempt number
        assert retry_info["exceptions"][1][1] == 1  # Second attempt number

    def test_preserves_function_metadata(self):
        """Test decorator preserves function metadata."""

        @retry_with_backoff(max_attempts=3)
        def my_function():
            """My docstring."""
            return "test"

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."

    def test_delay_timing(self):
        """Test that retry delays are applied."""
        with patch("time.sleep") as mock_sleep:
            call_count = {"value": 0}

            @retry_with_backoff(
                max_attempts=3,
                initial_delay=1.0,
                exponential_base=2.0,
                jitter=False,
            )
            def flaky_function():
                call_count["value"] += 1
                if call_count["value"] < 2:
                    raise ValueError("Error")
                return "success"

            result = flaky_function()

            assert result == "success"
            # Should have slept once (between attempt 1 and 2)
            assert mock_sleep.call_count == 1
            # First retry delay should be 1.0
            mock_sleep.assert_called_with(1.0)


class TestRetryableOperation:
    """Test RetryableOperation context manager."""

    def test_init(self):
        """Test initialization."""
        retry = RetryableOperation(max_attempts=5, initial_delay=0.5)
        assert retry.config.max_attempts == 5
        assert retry.config.initial_delay == 0.5
        assert retry.current_attempt == 0
        assert retry.last_exception is None

    def test_success_first_attempt(self):
        """Test successful operation on first attempt."""
        retry = RetryableOperation(max_attempts=3)
        attempt_count = 0

        for attempt in retry:
            with attempt:
                attempt_count += 1
                result = "success"
                break

        assert result == "success"
        assert attempt_count == 1

    def test_success_after_retries(self):
        """Test successful operation after retries."""
        retry = RetryableOperation(max_attempts=3, initial_delay=0.01)
        attempt_count = 0

        for attempt in retry:
            with attempt:
                attempt_count += 1
                if attempt_count < 2:
                    raise ValueError("Temporary error")
                result = "success"
                break

        assert result == "success"
        assert attempt_count == 2

    def test_all_attempts_fail(self):
        """Test operation that fails all attempts."""
        retry = RetryableOperation(max_attempts=3, initial_delay=0.01)
        attempt_count = 0

        with pytest.raises(ValueError, match="Always fails"):
            for attempt in retry:
                with attempt:
                    attempt_count += 1
                    raise ValueError("Always fails")

        assert attempt_count == 3

    def test_iterator_protocol(self):
        """Test iterator protocol."""
        retry = RetryableOperation(max_attempts=3)

        # Should be iterable
        iterator = iter(retry)
        assert iterator is retry

        # Should produce RetryAttempt objects
        attempt = next(iterator)
        assert isinstance(attempt, RetryAttempt)

    def test_stop_iteration(self):
        """Test StopIteration when max attempts reached."""
        retry = RetryableOperation(max_attempts=2)

        # Consume both attempts without errors
        for attempt in retry:
            with attempt:
                pass

        # Trying to iterate again should raise StopIteration
        retry_iter = iter(retry)
        next(retry_iter)  # First attempt
        next(retry_iter)  # Second attempt

        with pytest.raises(StopIteration):
            next(retry_iter)  # Should raise


class TestRetryAttempt:
    """Test RetryAttempt context manager."""

    def test_init(self):
        """Test initialization."""
        operation = RetryableOperation()
        attempt = RetryAttempt(operation, 0)

        assert attempt.operation is operation
        assert attempt.attempt_number == 0

    def test_successful_attempt(self):
        """Test successful attempt context."""
        operation = RetryableOperation()
        attempt = RetryAttempt(operation, 0)

        with attempt:
            result = "success"

        assert result == "success"
        assert operation.last_exception is None

    def test_failed_attempt_stores_exception(self):
        """Test failed attempt stores exception."""
        operation = RetryableOperation()
        attempt = RetryAttempt(operation, 0)

        exception = ValueError("Test error")

        # Manually trigger __exit__ with exception
        attempt.__enter__()
        suppress = attempt.__exit__(ValueError, exception, None)

        assert operation.last_exception is exception
        assert suppress is True  # Exception should be suppressed to allow retry

    def test_last_attempt_failure_reraises(self, caplog):
        """Test that last attempt failure re-raises exception."""
        import logging

        caplog.set_level(logging.ERROR)
        operation = RetryableOperation(max_attempts=3)
        attempt = RetryAttempt(operation, 2)  # Last attempt (0-indexed)

        exception = ValueError("Final error")

        # Manually trigger __exit__ with exception
        attempt.__enter__()
        suppress = attempt.__exit__(ValueError, exception, None)

        assert suppress is False  # Should not suppress, will re-raise
        assert "failed after 3 attempts" in caplog.text.lower()

    def test_delay_applied_on_retry(self):
        """Test delay is applied when retrying."""
        with patch("time.sleep") as mock_sleep:
            operation = RetryableOperation(max_attempts=3, initial_delay=1.0, jitter=False)
            attempt = RetryAttempt(operation, 0)

            exception = ValueError("Test error")

            attempt.__enter__()
            attempt.__exit__(ValueError, exception, None)

            # Should have slept
            mock_sleep.assert_called_once()
            # First attempt delay should be 1.0
            assert mock_sleep.call_args[0][0] == 1.0


class TestAsyncRetryWithBackoff:
    """Test async_retry_with_backoff decorator."""

    @pytest.mark.asyncio
    async def test_success_first_attempt(self):
        """Test successful async function on first attempt."""
        call_count = {"value": 0}

        @async_retry_with_backoff(max_attempts=3)
        async def successful_function():
            call_count["value"] += 1
            return "success"

        result = await successful_function()

        assert result == "success"
        assert call_count["value"] == 1

    @pytest.mark.asyncio
    async def test_success_after_retries(self, caplog):
        """Test successful async function after retries."""
        import logging

        caplog.set_level(logging.WARNING)
        call_count = {"value": 0}

        @async_retry_with_backoff(max_attempts=3, initial_delay=0.01)
        async def flaky_function():
            call_count["value"] += 1
            if call_count["value"] < 2:
                raise ValueError("Temporary error")
            return "success"

        result = await flaky_function()

        assert result == "success"
        assert call_count["value"] == 2
        assert "retrying" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_all_attempts_fail(self, caplog):
        """Test async function that fails all retry attempts."""
        import logging

        caplog.set_level(logging.ERROR)
        call_count = {"value": 0}

        @async_retry_with_backoff(max_attempts=3, initial_delay=0.01)
        async def always_fails():
            call_count["value"] += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            await always_fails()

        assert call_count["value"] == 3
        assert "failed after 3 attempts" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_specific_exceptions_only(self):
        """Test that only specified exceptions are retried in async."""
        call_count = {"value": 0}

        @async_retry_with_backoff(max_attempts=3, exceptions=(ValueError,), initial_delay=0.01)
        async def raises_type_error():
            call_count["value"] += 1
            raise TypeError("Not retried")

        with pytest.raises(TypeError, match="Not retried"):
            await raises_type_error()

        # Should fail immediately, not retry
        assert call_count["value"] == 1

    @pytest.mark.asyncio
    async def test_on_retry_callback(self):
        """Test on_retry callback is called in async."""
        retry_info = {"count": 0}

        def on_retry_callback(exception, attempt):
            retry_info["count"] += 1

        call_count = {"value": 0}

        @async_retry_with_backoff(
            max_attempts=3,
            initial_delay=0.01,
            on_retry=on_retry_callback,
        )
        async def flaky_function():
            call_count["value"] += 1
            if call_count["value"] < 2:
                raise ValueError("Error")
            return "success"

        result = await flaky_function()

        assert result == "success"
        assert retry_info["count"] == 1

    @pytest.mark.asyncio
    async def test_preserves_function_metadata(self):
        """Test async decorator preserves function metadata."""

        @async_retry_with_backoff(max_attempts=3)
        async def my_async_function():
            """My async docstring."""
            return "test"

        assert my_async_function.__name__ == "my_async_function"
        assert my_async_function.__doc__ == "My async docstring."

    @pytest.mark.asyncio
    async def test_delay_timing(self):
        """Test that async retry delays are applied."""

        # Create a properly awaitable mock
        async def mock_async_sleep(delay):
            pass

        with patch("asyncio.sleep", side_effect=mock_async_sleep) as mock_sleep:
            call_count = {"value": 0}

            @async_retry_with_backoff(
                max_attempts=3,
                initial_delay=1.0,
                exponential_base=2.0,
                jitter=False,
            )
            async def flaky_function():
                call_count["value"] += 1
                if call_count["value"] < 2:
                    raise ValueError("Error")
                return "success"

            result = await flaky_function()

            assert result == "success"
            # Should have slept once (between attempt 1 and 2)
            assert mock_sleep.call_count == 1
            # First retry delay should be 1.0
            mock_sleep.assert_called_with(1.0)
