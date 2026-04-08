import pathlib
from api.services.text_extraction import extract_text_from_local
from api.services.rag.ingestion.parsers import is_text_junk

def test_file(p):
    path = pathlib.Path(p)
    text = extract_text_from_local(path)
    if text is None:
        print("FAILED: extract_text_from_local returned None")
        return
    
    print(f"Extracted Text Length: {len(text)}")
    junk = is_text_junk(text)
    print(f"Is Junk? {junk}")
    
    if not junk:
        print("SUCCESS: File should have been indexed.")
    else:
        # Diagnostic for junk check
        alnum_count = sum(1 for c in text if c.isalnum() or c.isspace())
        ratio = alnum_count / len(text)
        print(f"Alnum Ratio: {ratio:.2f}")
        sample = text[:500]
        if len(sample) > 50:
            counts = [sample.count(c) for c in set(sample)]
            most_common = max(counts)
            print(f"Max char repetition: {most_common/len(sample):.2f}")

if __name__ == "__main__":
    import sys
    test_file(sys.argv[1])
