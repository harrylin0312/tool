"""Validate the reviewed sample data and rebuild the reader's HTML seed."""
import json,re
from pathlib import Path
root=Path(__file__).resolve().parent
data=json.loads((root/'sample-data.json').read_text())
words=set(re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)*",' '.join(data['paragraphs']).lower()))
assert not words-data['lexicon'].keys(),'Missing glossary entries'
for word,e in data['lexicon'].items():
 assert e['meaning'] and e['pos'],word
 if e['scope']=='covered' and e.get('matchType')!='compound':assert e.get('level') in range(1,7),(word,'Missing level')
 if e.get('level'):assert e.get('sourcePage') and e.get('levelSource'),word
book={'id':'neuromancer-english-sample','title':'Neuromancer','author':'William Gibson','sample':True,'chapters':[{'title':'Part One · Chiba City Blues 01','paragraphs':data['paragraphs'],'sourcePage':3}]}
text=(root/'template.html').read_text().replace('/*__BOOK__*/',json.dumps(book,ensure_ascii=False)).replace('/*__LEXICON__*/',json.dumps(data['lexicon'],ensure_ascii=False))
assert 'word-data' in text and 'app.js?v=2' in text
(root/'index.html').write_text(text)
print(f'Verified {len(words)} unique body words, levels, and source references; rebuilt index.html')
