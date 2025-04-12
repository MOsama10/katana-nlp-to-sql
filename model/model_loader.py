from langchain_community.llms import LlamaCpp
import os

def load_sqlcoder_llm():
    model_path = os.path.abspath("models/sqlcoder-gguf/sqlcoder-7b-2.Q4_K_M.gguf")

    llm = LlamaCpp(
        model_path=model_path,
        n_ctx=2048,
        n_batch=256,
        temperature=0.1,
        max_tokens=256,
        top_p=0.95,
        f16_kv=False,  # ✅ Force CPU mode
        verbose=True
    )

    return llm
