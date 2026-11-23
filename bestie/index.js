const categories = {
  all: '全部',
  stage: '打歌舞台',
  program: '節目與訪談',
  camera: '直拍與全景',
  behind: '練習與幕後'
};
const results = document.querySelector('#results');
const status = document.querySelector('#count');
const search = document.querySelector('#search');
const order = document.querySelector('#order');
const filters = document.querySelector('#filters');
const template = document.querySelector('#event');
let selected = 'all';

function categoryOf(event, format) {
  if (event.dateLabel === '播出' && event.videos[0][1] === '播出舞台') {
    return format === '播出舞台' ? 'stage' : 'camera';
  }
  return /舞蹈|幕後/.test(format) ? 'behind' : 'program';
}

function normalize(value) {
  return value.normalize('NFKC').toLowerCase().replace(/[./-]/g, '').trim();
}

function createEvent(event, videos) {
  const fragment = template.content.cloneNode(true);
  const date = fragment.querySelector('time');
  date.dateTime = event.date;
  date.textContent = event.date.replaceAll('-', '.');
  fragment.querySelector('.event-date span').textContent = event.dateLabel;
  fragment.querySelector('.show').textContent = event.show + ' ／ ' + event.channel;
  fragment.querySelector('h3').textContent = event.title;
  fragment.querySelector('.note').textContent = event.note;

  const list = fragment.querySelector('.videos');
  for (const [id, format, member] of videos) {
    const item = document.createElement('li');
    const link = document.createElement('a');
    link.href = 'https://www.youtube.com/watch?v=' + id;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = member ? member.split(' ').slice(0, 2).join(' ') + ' · ' + format : format;
    link.setAttribute('aria-label', [event.date, event.show, event.title, link.textContent, 'YouTube（新分頁）'].join('，'));
    item.append(link);
    list.append(item);
  }
  return fragment;
}

function render() {
  const words = normalize(search.value).split(/\s+/).filter(Boolean);
  const visible = [];
  let videoCount = 0;
  const list = order.value === 'old' ? [...events].reverse() : events;

  for (const event of list) {
    const videos = event.videos.filter(([, format, member]) => {
      const matchesCategory = selected === 'all' || categoryOf(event, format) === selected;
      const metadata = normalize([
        event.date, event.date.slice(2), event.show, event.channel, event.title,
        event.note, format, member, member && '直拍 fancam', categories[categoryOf(event, format)]
      ].join(' '));
      return matchesCategory && words.every(word => metadata.includes(word));
    });
    if (videos.length) {
      visible.push(createEvent(event, videos));
      videoCount += videos.length;
    }
  }

  status.textContent = visible.length + ' 個場次／節目 · ' + videoCount + ' 支影片';
  results.replaceChildren();
  if (visible.length) {
    const heading = document.createElement('h2');
    heading.className = 'sr-only';
    heading.textContent = categories[selected];
    results.append(heading, ...visible);
  } else {
    const message = document.createElement('p');
    message.className = 'empty';
    message.textContent = '找不到符合條件的影片。試試其他關鍵字或選擇「全部」。';
    results.append(message);
  }
}

for (const [key, label] of Object.entries(categories)) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  button.setAttribute('aria-pressed', String(key === selected));
  button.addEventListener('click', () => {
    selected = key;
    for (const filter of filters.children) {
      filter.setAttribute('aria-pressed', String(filter === button));
    }
    render();
  });
  filters.append(button);
}

document.querySelector('#period').textContent =
  events.at(-1).date.replaceAll('-', '.') + ' — ' + events[0].date.replaceAll('-', '.');
search.addEventListener('input', render);
order.addEventListener('change', render);
render();
