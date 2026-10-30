"""Rebuild the standalone reader from reviewed sample data; Python 3 only."""
import json,re
from pathlib import Path
root=Path(__file__).resolve().parent
data=json.loads((root/'sample-data.json').read_text())
words=set(re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)*",' '.join(data['paragraphs']).lower()))
assert not words-data['lexicon'].keys(),'Missing glossary entries'
assert all(e['meaning'] and e['pos'] for e in data['lexicon'].values())
(root/'index.html').write_text((root/'template.html').read_text().replace('/*__BOOK__*/',json.dumps(data,ensure_ascii=False)))
print(f"Verified {len(words)} unique body words; rebuilt index.html")
