const members = ['惠妍 Hyeyeon 혜연', '有智 U.Ji 유지', '多惠 Dahye 다혜', '海嶺 Haeryung 해령'];

function cameras(ids, format = '成員直拍') {
  return ids.map((id, index) => [id, format, members[index]]);
}

function musicShow(date, show, channel, stage, angles, note = '打歌舞台') {
  return {
    date: '2026-' + date,
    dateLabel: '播出',
    show,
    channel,
    title: 'Love Options (연애의 조건)',
    note,
    videos: [[stage, '播出舞台'], ...angles]
  };
}

const events = [
  {
    date: '2026-11-22', dateLabel: '上架', show: 'Dahye 的 Vlog', channel: '다혜가다했다DAHYE',
    title: 'BESTie 第二週打歌幕後', note: 'Dahye 記錄重組後第二週的音樂節目活動。原片名為「어른여자 생활 | 베스티 음방 브이로그」。',
    videos: [['o8W6FYVoaBE', '幕後 Vlog · 17:10']]
  },
  musicShow('11-22', '人氣歌謠 · Inkigayo', 'SBSKPOP X INKIGAYO', 'z00UvsqpRVw', [
    ['IcRNaHh4rZI', '團體全景 4K'],
    ...cameras(['9ssxKwwnDIc', 'zVujYDsf7DM']),
    ['sWtjZnBaQsM', '臉部特寫', members[2]],
    ['RS01eGoljUo', '臉部特寫', members[3]]
  ]),
  {
    date: '2026-11-21', dateLabel: '上架', show: '밥묵자', channel: '꼰대희',
    title: 'BESTie 全員聚餐訪談', note: '四人帶菜赴約，聊歌曲翻紅與重組經過。',
    videos: [['prw6wJGJroI', '完整節目']]
  },
  musicShow('11-20', '音樂銀行 · Music Bank', 'KBS Kpop', 'iVUTvsSFG3A', [
    ['Ju1Qx03u9hg', '團體一鏡到底 4K'],
    ...cameras(['EaCY-sXgchI', 'OyrJXMIJIr8', 'NBU7Ej-W1G8', '9NuKa9L4n8g'], '直式直拍'),
    ...cameras(['B-ePpVCVztc', 'z9HdEMyn3jA', 'mBIajarKjZ8', 'hMkzCr0wP8M'], '臉部特寫')
  ]),
  {
    date: '2026-11-18', dateLabel: '播出', show: '兩點逃出 Cultwo Show · 두시탈출 컬투쇼', channel: 'SBS Radio 에라오',
    title: '重組後首次電台通告', note: '四人一起受訪，並現場演唱〈Love Options〉。',
    videos: [['lZVbK5Iz-_A', '完整電台節目'], ['syugNuGvOX8', '電台 Live · Love Options']]
  },
  musicShow('11-15', '人氣歌謠 · Inkigayo', 'SBSKPOP X INKIGAYO', 'kBvCCRnp8ZM', [
    ['s0Fe8Ig8-3E', '團體全景 4K'],
    ...cameras(['Fr7yEeMph4c', '9x5KwrcaOgQ', 'IihZA29d-QA', 'lP6arYLUMAM'])
  ], '第 1331 集'),
  musicShow('11-14', 'Show! 音樂中心 · Music Core', 'MBCkpop', 'yWuDTKE3gUE', [
    ['pUy86Llo-tk', '團體全景'],
    ...cameras(['5mx5_Y-lVu0', 'KWCo_DQtx4Q', 'eA0n38xl_3U', '3UyRJ7oUyUI'])
  ]),
  musicShow('11-13', '音樂銀行 · Music Bank', 'KBS Kpop', 'InaRJ8kI8qE', [
    ...cameras(['s70WVtaiMP8', 'DHcLy-kYIeA', 'TNhLxrXPQa4', 'LnqLll2mfYM'])
  ]),
  {
    date: '2026-11-10', dateLabel: '上架', show: '릴레이마이크', channel: '원마이크',
    title: '回歸舞台後的四人訪談', note: '全員聊〈Love Options〉翻紅與再登上打歌舞台。',
    videos: [['eYK7YecTeYg', '短訪談']]
  },
  {
    date: '2026-11-08', dateLabel: '上架', show: 'Dahye 的 Vlog', channel: '다혜가다했다DAHYE',
    title: '從重聚到打歌的幕後', note: 'Dahye 記錄成員重聚、舞蹈影片拍攝與回歸舞台準備。',
    videos: [['fU0tybevRVs', '幕後 Vlog']]
  },
  {
    date: '2026-11-07', dateLabel: '上架', show: 'Relay Dance · 릴레이댄스', channel: 'M2',
    title: 'Love Options (연애의 조건)', note: '四人接力舞蹈。',
    videos: [['L59TW3qY8ug', '接力舞蹈 4K']]
  },
  musicShow('10-31', 'Show! 音樂中心 · Music Core', 'MBCkpop', 'o6KvKuSviA0', [
    ['ms1xrjx2ehw', '團體全景']
  ], '重組回歸特別舞台'),
  {
    date: '2026-10-29', dateLabel: '上架', show: 'Dahye 的 YouTube 頻道', channel: '다혜가다했다DAHYE',
    title: 'Love Options (연애의 조건)', note: '四人重新拍攝的 2026 年版舞蹈練習。',
    videos: [['Z-pAsnR3lsM', '舞蹈練習']]
  },
  {
    date: '2026-11-23', dateLabel: '播出', show: 'JTBC 아침&', channel: 'JTBC News',
    title: 'Hyeyeon 擔任一日氣象主播', guests: [members[0]],
    videos: [['tH25Xmh9_dI', '氣象播報']]
  },
  {
    date: '2026-11-20', dateLabel: '上架', show: 'Suit Dance · 수트댄스', channel: '1theK Originals',
    title: 'Love Options (연애의 조건)',
    videos: [['FVNI7zBuk-4', '西裝舞蹈表演 4K']]
  },
  {
    date: '2026-11-18', dateLabel: '播出', show: 'Cultwo Show · 두시탈출 컬투쇼', channel: 'SBS Radio 에라오',
    title: 'U.Ji 演唱〈Let It Go〉', guests: [members[1]],
    videos: [['aNLz9WgH0PY', '個人演唱片段']]
  },
  {
    date: '2026-11-18', dateLabel: '播出', show: '裴成宰的 TEN · 배성재의 텐', channel: '배성재의 텐 (Bae_ten)',
    title: 'Hyeyeon、Haeryung 作客《Produce 1077》', guests: [members[0], members[3]],
    videos: [['IWzNzAvSDsY', '電台訪談']]
  },
  {
    date: '2026-11-13', dateLabel: '上架', show: '차오룸 第 47 集', channel: '차오루',
    title: 'Dahye、Haeryung 作客曹璐的節目', guests: [members[2], members[3]],
    videos: [['KR4dvtxslQI', '網路節目']]
  },
  {
    date: '2026-11-10', dateLabel: '播出', show: 'KBS 뉴스라인 W', channel: 'KBS News',
    title: 'Hyeyeon、Haeryung 談 BESTie 重組', guests: [members[0], members[3]],
    videos: [['7MC7PacW-7k', '新聞訪談']]
  },
  {
    date: '2026-11-09', dateLabel: '播出', show: 'The Trot Show · 더 트롯쇼', channel: 'THE 트롯 보라고',
    title: 'Hyeyeon〈믿지못할 남자〉', guests: [members[0]],
    videos: [['b0hNOJ-5MTg', '個人舞台']]
  },
  {
    date: '2026-10-24', dateLabel: '上架', show: 'Dahye 的 YouTube 頻道', channel: '다혜가다했다DAHYE',
    title: 'Dahye 的偶像知道她？', guests: [members[2]], note: '최애가 나를 안다고?',
    videos: [['ILqM8yV40AA', 'Shorts · 0:28']]
  },
  {
    date: '2026-10-22', dateLabel: '上架', show: 'Dahye 的 YouTube 頻道', channel: '다혜가다했다DAHYE',
    title: 'Dahye「我要應徵 BESTie 主唱」', guests: [members[2]], note: '베스티 메인보컬 지원합니다',
    videos: [['v3EPVDgBgE8', 'Shorts · 0:19']]
  },
  {
    date: '2026-10-18', dateLabel: '上架', show: 'Dahye 的 Vlog', channel: '다혜가다했다DAHYE',
    title: 'Dahye 的秋日吃蝦日常', guests: [members[2]], note: '가을철 남들은 결혼할 때, 나는 대하를 먹어...',
    videos: [['rAs_S8gdwWw', '個人 Vlog · 34:22']]
  },
].sort((first, second) => second.date.localeCompare(first.date));
