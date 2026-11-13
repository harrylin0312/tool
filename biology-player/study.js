(() => {
  'use strict';
  const host = document.getElementById('study');
  const data = window.BIO_STUDY;
  const answers = new Map();
  let mode = 'map';
  const el = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
  const time = t => { const n = Math.floor(t); return [Math.floor(n / 3600), Math.floor(n / 60) % 60, n % 60].map(v => String(v).padStart(2, '0')).join(':'); };
  function button(text, fn, cls) { const b = el('button', text, cls); b.type = 'button'; b.addEventListener('click', fn); return b; }
  function replay(id, start) {
    const target = lessons.findIndex(v => v.id === id);
    if (target < 0) return;
    const go = () => { seek(start); setStatus('課堂整理 → ' + time(start)); video.play().catch(() => setStatus('已跳到 ' + time(start) + '，請按播放。')); };
    if (target !== index) { loadLesson(target); video.addEventListener('loadedmetadata', go, { once: true }); }
    else if (video.readyState >= 1) go();
    else video.addEventListener('loadedmetadata', go, { once: true });
    document.getElementById('screen').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
  }
  function sources(topic) {
    const list = el('div', null, 'study-sources');
    topic.sources.forEach(s => { const a = el('a', s.label); a.href = s.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; list.append(a); });
    return list;
  }
  function topicCard(id, topic) {
    const details = el('details', null, 'study-topic');
    details.dataset.search = [topic.title, topic.idea, ...topic.bullets, topic.pitfall].join(' ').toLowerCase();
    const summary = el('summary'); summary.append(el('span', topic.title, 'study-topic-title'), el('span', topic.idea, 'study-topic-idea')); details.append(summary);
    const body = el('div', null, 'study-topic-body');
    const list = el('ul'); topic.bullets.forEach(s => list.append(el('li', s))); body.append(list);
    if (topic.pitfall) { const tip = el('p', null, 'study-trap'); tip.append(el('strong', '容易混淆　'), document.createTextNode(topic.pitfall)); body.append(tip); }
    body.append(button('↗ ' + time(topic.start) + ' 回看這段', () => replay(id, topic.start), 'study-replay'));
    const evidence = el('details', null, 'study-evidence'); evidence.append(el('summary', '查看逐字稿依據'));
    evidence.append(el('p', '以下保留逐字稿原文，可能仍有辨識誤差；整理筆記不是逐字引述。', 'study-small'));
    topic.evidence.forEach(cue => { const b = button(time(cue.start) + '　' + cue.text, () => replay(id, cue.start), 'study-quote'); b.setAttribute('aria-label', '回看字幕第 ' + cue.cueId + ' 條：' + cue.text); evidence.append(b); });
    body.append(evidence);
    if (topic.sources.length) body.append(sources(topic));
    details.append(body); return details;
  }
  function mapPanel(id, lesson) {
    const panel = document.getElementById('study-map'); panel.replaceChildren();
    const root = el('div', null, 'study-map-root'); root.append(el('span', '這堂課的核心路徑', 'study-small'), el('strong', lesson.title)); panel.append(root);
    const filter = el('input'); filter.type = 'search'; filter.placeholder = '找概念，例如：測交、內含子、同源'; filter.setAttribute('aria-label', '搜尋這堂課的整理概念'); filter.className = 'study-filter'; panel.append(filter);
    const tools = el('div', null, 'study-map-tools'); tools.append(button('展開全部重點', () => panel.querySelectorAll('.study-topic').forEach(d => { if (!d.hidden) d.open = true; })), button('收合重點', () => panel.querySelectorAll('.study-topic').forEach(d => d.open = false))); panel.append(tools);
    const grid = el('div', null, 'study-map-grid');
    lesson.groups.forEach(g => {
      const branch = el('section', null, 'study-branch'); branch.append(el('h3', g.title), el('p', g.link, 'study-branch-link'));
      g.topics.forEach(t => branch.append(topicCard(id, t))); grid.append(branch);
    }); panel.append(grid);
    const empty = el('p', '沒有符合的概念，試試其他關鍵字。', 'study-small'); empty.hidden = true; panel.append(empty);
    filter.addEventListener('input', () => { const q = filter.value.trim().toLowerCase(); let total = 0; grid.querySelectorAll('.study-branch').forEach(branch => { let visible = 0; branch.querySelectorAll('.study-topic').forEach(t => { t.hidden = !t.dataset.search.includes(q); if (!t.hidden) visible++; }); branch.hidden = visible === 0; total += visible; }); empty.hidden = total !== 0; });
  }
  function tablePanel(lesson) {
    const panel = document.getElementById('study-tables'); panel.replaceChildren();
    lesson.comparisons.forEach(comp => { const card = el('section', null, 'study-table-card'); card.append(el('h3', comp.title)); const wrap = el('div', null, 'study-table-wrap'); wrap.tabIndex = 0; wrap.setAttribute('aria-label', comp.title + '，可左右捲動'); const table = el('table'), head = el('thead'), row = el('tr'); comp.heads.forEach(s => { const th = el('th', s); th.scope = 'col'; row.append(th); }); head.append(row); table.append(head); const body = el('tbody'); comp.rows.forEach(r => { const tr = el('tr'); r.forEach((s, i) => { const c = el(i === 0 ? 'th' : 'td', s); if (i === 0) c.scope = 'row'; tr.append(c); }); body.append(tr); }); table.append(body); wrap.append(table); card.append(wrap, el('p', comp.note, 'study-small')); panel.append(card); });
    const flow = el('section', null, 'study-table-card'); flow.append(el('h3', '讀題順序'));
    const steps = lesson.date.includes('11-03') ? ['先認分裂階段與配子來源', '判斷基因位是否獨立／連鎖', '分開寫基因型與表現型', '最後套入題目條件與機率'] : ['先認基因、染色體或分類層次', '寫出題目提供的確定條件', '找出元件功能或共同祖先', '核對例外，不直接套課堂口訣'];
    const list = el('ol', null, 'study-flow'); steps.forEach(s => list.append(el('li', s))); flow.append(list); panel.append(flow);
  }
  function quizPanel(id, lesson) {
    const panel = document.getElementById('study-quiz'); panel.replaceChildren();
    const score = el('p', null, 'study-score'); score.setAttribute('role', 'status'); panel.append(score);
    const updateScore = () => { const results = lesson.quiz.map((q, i) => answers.get(id + ':' + i)).filter(v => v !== undefined); const right = lesson.quiz.filter((q, i) => answers.get(id + ':' + i) === q.answer).length; score.textContent = `已作答 ${results.length}／${lesson.quiz.length} 題 · 答對 ${right} 題`; };
    lesson.quiz.forEach((q, i) => {
      const card = el('section', null, 'study-question'); card.append(el('h3', (i + 1) + '. ' + q.q)); const choices = el('div', null, 'study-choices'); choices.setAttribute('role', 'group'); choices.setAttribute('aria-label', q.q);
      const feedback = el('p', null, 'study-feedback'); feedback.setAttribute('role', 'status'); const buttons = [];
      const show = picked => { buttons.forEach((b, n) => { b.disabled = true; b.classList.toggle('correct', n === q.answer); b.classList.toggle('incorrect', n === picked && picked !== q.answer); }); feedback.textContent = (picked === q.answer ? '答對了。' : '再釐清一下：') + q.explain; feedback.hidden = false; updateScore(); };
      q.choices.forEach((choice, n) => { const b = button(String.fromCharCode(65 + n) + '　' + choice, () => { answers.set(id + ':' + i, n); show(n); }); buttons.push(b); choices.append(b); });
      card.append(choices, feedback); const topic = lesson.groups.flatMap(g => g.topics).find(t => t.title === q.topic); if (topic) card.append(button('↗ 回看這個觀念 ' + time(topic.start), () => replay(id, topic.start), 'study-replay'));
      panel.append(card); const previous = answers.get(id + ':' + i); if (previous !== undefined) show(previous); else feedback.hidden = true;
    });
    panel.append(button('重新作答這堂課', () => { lesson.quiz.forEach((q, i) => answers.delete(id + ':' + i)); quizPanel(id, lesson); })); updateScore();
  }
  function setMode(next) {
    mode = next; const tabs = [...host.querySelectorAll('[data-study-mode]')];
    tabs.forEach(tab => { const selected = tab.dataset.studyMode === next; tab.setAttribute('aria-selected', String(selected)); tab.tabIndex = selected ? 0 : -1; });
    ['map', 'tables', 'quiz'].forEach(key => document.getElementById('study-' + key).hidden = key !== next);
  }
  function render() {
    const id = current().id, lesson = data[id]; if (!lesson) { host.hidden = true; return; } host.hidden = false;
    document.getElementById('study-title').textContent = lesson.date + '｜' + lesson.title;
    document.getElementById('study-meta').textContent = lesson.groups.reduce((s, g) => s + g.topics.length, 0) + ' 個概念 · 2 張比較表 · 6 題自測';
    mapPanel(id, lesson); tablePanel(lesson); quizPanel(id, lesson); setMode(mode);
  }
  host.querySelectorAll('[data-study-mode]').forEach(tab => {
    tab.addEventListener('click', () => setMode(tab.dataset.studyMode));
    tab.addEventListener('keydown', e => { const list = [...host.querySelectorAll('[data-study-mode]')]; let i = list.indexOf(tab); if (e.key === 'ArrowRight') i = (i + 1) % list.length; else if (e.key === 'ArrowLeft') i = (i + list.length - 1) % list.length; else if (e.key === 'Home') i = 0; else if (e.key === 'End') i = list.length - 1; else return; e.preventDefault(); setMode(list[i].dataset.studyMode); list[i].focus(); });
  });
  window.addEventListener('biology:lesson-change', render);
  render();
})();
