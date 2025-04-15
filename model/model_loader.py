from langchain_community.llms import LlamaCpp
import os
from functools import lru_cache

@lru_cache(maxsize=1)
def load_sqlcoder_llm():
    """Load the SQLCoder LLM with caching to prevent multiple loads.
    Uses optimized settings for better performance with limited resources."""
    model_path = os.path.abspath("models/sqlcoder-gguf/sqlcoder-7b-2.Q4_K_M.gguf")

    llm = LlamaCpp(
        model_path=model_path,
        n_ctx=2048,  # Set to match exact context window
        n_batch=512,  # Keep batch size large for faster processing
        temperature=0.01,  # Lower temperature for more deterministic results
        max_tokens=256,  # Reduced to speed up generation
        top_p=0.9,
        f16_kv=True,  # Enable for hardware that supports it
        verbose=False,
        repeat_penalty=1.1,  # Slightly reduced for faster generation
        stop=["```", ";"],  # Add stop sequences to prevent needless generation
        n_threads=max(1, os.cpu_count() - 1),  # Use all available threads except one
        # Lightweight model settings to reduce memory usage
        model_kwargs={
            "use_mlock": True,
            "mmap": True,
            "low_vram": False,  # Set to False if enough RAM is available for better speed
            "seed": 42          # Consistent seed for deterministic results
        }
    )

    return llm
