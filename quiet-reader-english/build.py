"""Validate Part One's complete text/glossary and rebuild the static reader."""
import json,re,hashlib
from pathlib import Path
root=Path(__file__).resolve().parent
book=json.loads((root/'part-one-book.json').read_text())
lexicon=json.loads((root/'part-one-lexicon.json').read_text())
pattern=r"[A-Za-z]+(?:['’-][A-Za-z]+)*"
chapters=book['chapters']
assert [c['number'] for c in chapters]==[1,2]
assert [len(c['paragraphs']) for c in chapters]==[222,166]
assert chapters[0]['paragraphs'][0].startswith('The sky above the port')
assert chapters[1]['paragraphs'][0].startswith('After a year of coffins')
assert chapters[1]['paragraphs'][-1].endswith('the drifting shoals of waste.')
assert book['partComplete'] and not book['completeBook']
words={m[0].lower().replace('’',"'") for c in chapters for p in c['paragraphs'] for m in re.finditer(pattern,p)}
assert not words-lexicon.keys(),f'Missing glossary: {words-lexicon.keys()}'
for word in words:
 e=lexicon[word]
 assert re.search(r'[\u4e00-\u9fff]',e['meaning']),(word,'Missing Chinese definition')
 assert e['pos'] and e['lemma'],word
 if e['scope']=='covered' and e.get('matchType')!='compound':assert e.get('level') in range(1,7),(word,'Missing level')
 if e.get('level'):assert e.get('sourcePage') and e.get('levelSource') and e.get('sourceEntry'),word
 if e.get('matchType')=='compound':assert e.get('components') and all(x['level'] in range(1,7) for x in e['components']),word
# Regression checks for ambiguous inflections and multiline source entries.
for form,base,level in [('found','find',1),('faded','fade',3),('cubes','cube',4),('dying','die',1),('tuned','tune',3),('deficiency','deficiency',6),('anywhere','anywhere',2)]:
 assert lexicon[form]['levelSource']==base and lexicon[form]['level']==level,form
text=(root/'template.html').read_text().replace('/*__BOOK__*/',json.dumps(book,ensure_ascii=False,separators=(',',':'))).replace('/*__LEXICON__*/',json.dumps(lexicon,ensure_ascii=False,separators=(',',':')))
assert 'word-data' in text and 'app.js?v=3-part-one' in text
(root/'index.html').write_text(text)
report={'part':1,'chapters':2,'sourcePdfPages':[3,42],'paragraphs':sum(len(c['paragraphs']) for c in chapters),'wordTokens':sum(len(re.findall(pattern,p)) for c in chapters for p in c['paragraphs']),'uniqueWords':len(words),'wordsWithChineseMeanings':len(words),'missingDefinitions':0,'missingCoveredLevels':0,'chapterWordCounts':[sum(len(re.findall(pattern,p)) for p in c['paragraphs']) for c in chapters],'indexSha256':hashlib.sha256(text.encode()).hexdigest()}
(root/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
