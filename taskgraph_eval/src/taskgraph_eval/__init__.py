"""TaskGraph Evaluation Harness - Tests LLM ability to transform partial DB snapshots."""

__version__ = "1.0.0"

from .executor import apply_ops
from .legality import validate_state
from .compare import compare_states
from .io_utils import read_json, write_json

__all__ = ["apply_ops", "validate_state", "compare_states", "read_json", "write_json"]
