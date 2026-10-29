from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
root=Path(__file__).parent
text='\n'.join(f'第{c}章 測試章節\n'+ '\n'.join(f'段落 {c}-{p:03d}。這是一段用來驗證長篇閱讀位置、重新排版以及章節排序的原創測試文字。風從海面吹來，紙頁輕輕翻動。' for p in range(120)) for c in range(1,4))
(root/'long-reading.txt').write_text(text,encoding='utf-8')
with ZipFile(root/'sample.epub','w',ZIP_DEFLATED) as z:
 z.writestr('mimetype','application/epub+zip')
 z.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="OEBPS/book.opf"/></rootfiles></container>')
 z.writestr('OEBPS/book.opf','<package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>EPUB 順序驗證</dc:title><dc:creator>靜讀測試</dc:creator></metadata><manifest><item id="b" href="second.xhtml"/><item id="a" href="first.xhtml"/></manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>')
 for name,title,body in [('first','第一章','這是第一段。'),('second','第二章','這是第二章的正文。')]:
  z.writestr(f'OEBPS/{name}.xhtml',f'<html><head><title>{title}</title></head><body><h1>{title}</h1><p>{body}</p><p>保留正確的章節順序。</p></body></html>')
