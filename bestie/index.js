const categories = {
  all: '全部',
  stage: '打歌',
  program: '節目',
  camera: '直拍',
  behind: '幕後'
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
  fragment.querySelector('.show-name').textContent = event.show;
  fragment.querySelector('.channel-name').textContent = event.channel;
  fragment.querySelector('h3').textContent = event.title;

  const list = fragment.querySelector('.videos');
  for (const [id, format, member] of videos) {
    const item = document.createElement('li');
    const link = document.createElement('a');
    link.href = 'https://www.youtube.com/watch?v=' + id;
    link.target = '_blank';
    if (format === '播出舞台') link.dataset.stage = '';
    link.rel = 'noopener noreferrer';
    const label = document.createElement('span');
    label.className = 'video-label';
    label.textContent = member ? member.split(' ')[1] + ' · ' + format : format;
    link.setAttribute('aria-label', [event.date, event.show, event.title, label.textContent, 'YouTube（新分頁）'].join('，'));

    const preview = document.createElement('span');
    preview.className = 'video-preview';
    const thumbnail = document.createElement('img');
    const thumbnailBase = 'https://i.ytimg.com/vi/' + id + '/';
    thumbnail.alt = '';
    thumbnail.width = 320;
    thumbnail.height = 180;
    thumbnail.loading = 'lazy';
    thumbnail.decoding = 'async';
    thumbnail.addEventListener('error', () => {
      thumbnail.addEventListener('error', () => thumbnail.remove(), { once: true });
      thumbnail.src = thumbnailBase + 'hqdefault.jpg';
    }, { once: true });
    thumbnail.src = thumbnailBase + 'mqdefault.jpg';
    preview.append(thumbnail);

    link.append(preview, label);
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

search.addEventListener('input', render);
order.addEventListener('change', render);
render();
