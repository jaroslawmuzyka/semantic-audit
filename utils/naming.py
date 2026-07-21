def safe_filename(url: str) -> str:
    """Deterministyczna zamiana URL -> nazwa pliku, używana przy eksporcie i przy
    odgadywaniu URL-a z powrotem po nazwie pliku (patrz utils/eeat_patch.py)."""
    return url.split('//')[-1].replace('/', '_').replace('?', '_')
