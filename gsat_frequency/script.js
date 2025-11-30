function isWebView() {
    const ua = navigator.userAgent || navigator.vendor || window.opera;
    // 常見 WebView 標記
    const webviewIndicators = ['wv', 'WebView', 'FBAN', 'FBAV', 'Instagram', 'Line'];
    return webviewIndicators.some(indicator => ua.includes(indicator));
}

function displayInfo(info) {
    const infoList = document.getElementById('info-list');
    infoList.innerHTML = '';
    for (const key in info) {
        const li = document.createElement('li');
        li.textContent = `${key}: ${info[key]}`;
        infoList.appendChild(li);
    }
}

async function getIP() {
    try {
        const response = await fetch('https://api.ipify.org?format=json');
        const data = await response.json();
        return data.ip;
    } catch (e) {
        return '無法取得 IP';
    }
}

async function collectDeviceInfo() {
    const info = {};

    // 瀏覽器名稱與版本
    const ua = navigator.userAgent;
    info['User-Agent'] = ua;
    let browserName = '未知';
    let browserVersion = '';
    if (ua.includes('Chrome')) {
        browserName = 'Chrome';
        browserVersion = ua.match(/Chrome\/([\d.]+)/)[1];
    } else if (ua.includes('Firefox')) {
        browserName = 'Firefox';
        browserVersion = ua.match(/Firefox\/([\d.]+)/)[1];
    } else if (ua.includes('Safari') && !ua.includes('Chrome')) {
        browserName = 'Safari';
        browserVersion = ua.match(/Version\/([\d.]+)/)[1];
    } else if (ua.includes('Edg')) {
        browserName = 'Edge';
        browserVersion = ua.match(/Edg\/([\d.]+)/)[1];
    }
    info['瀏覽器名稱'] = browserName;
    info['瀏覽器版本'] = browserVersion;

    // 作業系統
    const platform = navigator.platform;
    const osVersionMatch = ua.match(/\(([^)]+)\)/);
    info['作業系統與版本'] = platform + (osVersionMatch ? ' / ' + osVersionMatch[1] : '');

    // 設備類別
    const isMobile = /Mobi|Android/i.test(ua);
    const isTablet = /Tablet|iPad/i.test(ua);
    info['設備類別'] = isTablet ? '平板' : (isMobile ? '手機' : '桌機');

    // 裝置名稱
    info['裝置名稱'] = '不可取得';

    // 語言 / 系統語言 / 鍵盤設定 / 地區設定
    info['語言'] = navigator.language;
    info['語言列表'] = navigator.languages.join(', ');

    // 螢幕參數
    info['螢幕長寬'] = `${window.screen.height}-${window.screen.width}`;
    info['螢幕實際渲染'] = `${window.innerHeight}-${window.innerWidth}`;
    info['色深'] = window.screen.colorDepth;

    // 網路資訊
    if ('connection' in navigator) {
        const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
        info['網路類型'] = conn.effectiveType || '未知';
        info['下行速度'] = conn.downlink ? conn.downlink + ' Mb/s' : '未知';
        info['省流模式'] = conn.saveData ? '是' : '否';
    } else {
        info['網路資訊'] = '不支援 Network Information API';
    }

    // IP
    info['IP 位址'] = await getIP();

    return info;
}

function getUserId() {
    let userId = localStorage.getItem('user_id');
    if (!userId) {
        userId = 'user_' + Math.random().toString(36).substr(2, 9);
        localStorage.setItem('user_id', userId);
    }
    return userId;
}

async function saveToFirestore(info) {
    if (isWebView()) {
        console.log('WebView 環境，不寫入 Firestore');
        return;
    }
    const userId = getUserId();

    // 取得北京時間（東8）格式 YYYY/MM/DD/hh:mm:ss
    const now = new Date();
    const formattedTime = now.toLocaleString('zh-TW', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    }).replace(/\//g, '/').replace(', ', '/');

    try {
        await db.collection('device_info').doc(userId).set({
            timestamp: formattedTime,
            '瀏覽器名稱': info['瀏覽器名稱'],
            '瀏覽器版本': info['瀏覽器版本'],
            '作業系統與版本': info['作業系統與版本'],
            '設備類別': info['設備類別'],
            '裝置名稱': info['裝置名稱'],
            '語言': info['語言'],
            '語言列表': info['語言列表'],
            '螢幕長寬': info['螢幕長寬'],
            '螢幕實際渲染': info['螢幕實際渲染'],
            '色深': info['色深'],
            '網路類型': info['網路類型'] || '',
            '下行速度': info['下行速度'] || '',
            '省流模式': info['省流模式'] || '',
            'IP 位址': info['IP 位址'],
            'User-Agent': info['User-Agent']
        });
        console.log('已成功儲存到 Firestore（順序調整，北京時間格式）');
    } catch (error) {
        console.error('儲存到 Firestore 失敗:', error);
    }
}

async function init() {
    const isWebviewEnv = isWebView();
    const messageDiv = document.getElementById('webview-message');
    const infoDiv = document.getElementById('info');

    if (isWebviewEnv) {
        messageDiv.style.display = 'block';
        infoDiv.style.display = 'none';
    } else {
        messageDiv.style.display = 'none';
        infoDiv.style.display = 'block';
        const deviceInfo = await collectDeviceInfo();
        displayInfo(deviceInfo);
        saveToFirestore(deviceInfo);
    }
}

init();
