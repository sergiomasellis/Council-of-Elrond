import importlib.util
from huggingface_hub import hf_hub_download
from sentence_transformers import CrossEncoder

def patch_zeranker():
    path = hf_hub_download("zeroentropy/zerank-2", "modeling_zeranker.py", revision="main")
    spec = importlib.util.spec_from_file_location("modeling_zeranker", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

patch_zeranker()  # patches CrossEncoder.predict
ce = CrossEncoder("zeroentropy/zerank-2", trust_remote_code=True)
print(ce.predict([("What is 2+2?", 4), ("What is 2+2?", "1 million")]))