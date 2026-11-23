"""Validate all completed parts and rebuild the static English reader."""
import json,re,hashlib
from pathlib import Path
root=Path(__file__).resolve().parent
book=json.loads((root/'reader-book.json').read_text())
lexicon=json.loads((root/'reader-lexicon.json').read_text())
pattern=r"[A-Za-z]+(?:['’-][A-Za-z]+)*"
chapters=book['chapters']
assert [c['number'] for c in chapters]==list(range(1,25))+[None]
assert len(chapters)==25 and chapters[-1]['kind']=='backmatter'
assert book['partsCompleted']==[1,2,3,4] and book['completeBook']
assert chapters[0]['paragraphs'][0].startswith('The sky above the port')
assert chapters[23]['paragraphs'][-1].endswith('He never saw Molly again.')
assert chapters[-1]['paragraphs'][-1].endswith('who know why.')
assert [c['number'] for c in chapters if c['partEnd']]==[2,7,12,23,24]
words={m[0].lower().replace('’',"'") for c in chapters for p in c['paragraphs'] for m in re.finditer(pattern,p)}
assert not words-lexicon.keys(),f'Missing glossary: {words-lexicon.keys()}'
for word,e in lexicon.items():
 assert re.search(r'[\u4e00-\u9fff]',e['meaning']),(word,'Missing Chinese definition')
 assert e['pos'] and e['lemma'],word
 if e['scope']=='covered' and e.get('matchType')!='compound':assert e.get('level') in range(1,7),(word,'Missing level')
 if e.get('level'):assert e.get('sourcePage') and e.get('levelSource') and e.get('sourceEntry'),word
 if e.get('matchType')=='compound':assert e.get('components') and all(x['level'] in range(1,7) for x in e['components']),word
# Regressions: false suffix matches must not turn names into unrelated vocabulary.
for form,base,level in [('found','find',1),('faded','fade',3),('cubes','cube',4),('dying','die',1),('tuned','tune',3),('deficiency','deficiency',6),('anywhere','anywhere',2),('rider','ride',1)]:
 assert lexicon[form]['levelSource']==base and lexicon[form]['level']==level,form
for word in ['denver','peter','orly','tally','wintermute','corto']:
 assert lexicon[word]['scope']=='name' and lexicon[word]['level'] is None,word
for word in ['case#common','may#name','chin#proper','cutter#proper','letter#i']:assert word in lexicon
text=(root/'template.html').read_text().replace('/*__BOOK__*/',json.dumps(book,ensure_ascii=False,separators=(',',':'))).replace('/*__LEXICON__*/',json.dumps(lexicon,ensure_ascii=False,separators=(',',':')))
assert 'word-data' in text and 'app.js?v=5-complete' in text
(root/'index.html').write_text(text)
parts=[]
for part in book['partsCompleted']:
 cs=[c for c in chapters if c['part']==part]
 parts.append({'part':part,'chapters':[c['number'] for c in cs],'sourcePdfPages':[min(c['sourceStartPage'] for c in cs),max(c['sourceEndPage'] for c in cs)],'paragraphs':sum(len(c['paragraphs']) for c in cs),'wordTokens':sum(len(re.findall(pattern,p)) for c in cs for p in c['paragraphs'])})
report={'completedParts':book['partsCompleted'],'chapters':24,'readingSections':25,'completeBook':True,'sourcePdfPages':[3,266],'paragraphs':sum(len(c['paragraphs']) for c in chapters),'wordTokens':sum(len(re.findall(pattern,p)) for c in chapters for p in c['paragraphs']),'uniqueWords':len(words),'wordsWithChineseMeanings':len(words),'missingDefinitions':0,'missingCoveredLevels':0,'parts':parts,'indexSha256':hashlib.sha256(text.encode()).hexdigest()}
(root/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False))
