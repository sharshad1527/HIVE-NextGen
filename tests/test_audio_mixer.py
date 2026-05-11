import pytest
import numpy as np
from core.audio_mixer import RingBuffer, LinearInterpolator

def test_ring_buffer_push_pop_basic():
    rb = RingBuffer(capacity=100, channels=2)
    assert rb.size == 0

    data = np.ones((50, 2), dtype=np.float32)
    pushed = rb.push(data)
    assert pushed == 50
    assert rb.size == 50

    out_data = rb.pop(30)
    assert out_data.shape == (30, 2)
    assert np.all(out_data == 1.0)
    assert rb.size == 20

def test_ring_buffer_wrap_around():
    rb = RingBuffer(capacity=10, channels=1)
    
    # Push 8 elements
    d1 = np.arange(8, dtype=np.float32).reshape(-1, 1)
    rb.push(d1)
    
    # Pop 5 elements
    rb.pop(5)
    assert rb.size == 3
    
    # Push 5 more elements, should wrap around
    d2 = np.arange(8, 13, dtype=np.float32).reshape(-1, 1)
    pushed = rb.push(d2)
    assert pushed == 5
    assert rb.size == 8
    
    # Pop 8 elements to verify wrap around data integrity
    out_data = rb.pop(8)
    expected = np.array([5, 6, 7, 8, 9, 10, 11, 12], dtype=np.float32).reshape(-1, 1)
    np.testing.assert_array_equal(out_data, expected)
    assert rb.size == 0

def test_ring_buffer_overflow():
    rb = RingBuffer(capacity=10, channels=1)
    d1 = np.ones((15, 1), dtype=np.float32)
    pushed = rb.push(d1)
    assert pushed == 10  # Should only push up to capacity
    assert rb.size == 10

def test_ring_buffer_clear():
    rb = RingBuffer(capacity=10, channels=1)
    rb.push(np.ones((5, 1), dtype=np.float32))
    assert rb.size == 5
    rb.clear()
    assert rb.size == 0
    assert rb.write_ptr == 0
    assert rb.read_ptr == 0

# These tests will fail with the current stateless LinearInterpolator,
# but they define the required behavior for the upcoming refactor.
def test_linear_interpolator_continuity():
    interpolator = LinearInterpolator()
    
    # Simulate an incoming stream of 100 samples
    original_data = np.linspace(0, 99, 100, dtype=np.float32).reshape(-1, 1)
    
    # Process in two chunks of 50
    chunk1 = original_data[:50]
    chunk2 = original_data[50:]
    
    # Resample to 200 total (100 each chunk)
    res1 = interpolator.resample(chunk1, original_sr=44100, target_sr=88200, target_frames=100)
    res2 = interpolator.resample(chunk2, original_sr=44100, target_sr=88200, target_frames=100)
    
    # The end of res1 and start of res2 should be continuous
    # With a simple stateless linspace, the phase resets. 
    # With a proper stateful interpolator, res1[-1] and res2[0] align properly.
    assert np.isclose(res1[-1, 0], 49.5, atol=0.5)
    assert np.isclose(res2[0, 0], 50.0, atol=0.5)

