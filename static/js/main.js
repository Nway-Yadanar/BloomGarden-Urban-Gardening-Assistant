(() => {
  'use strict';




  /* ==========================
   * Utilities
   * ========================== */

  const $ = (sel, root = document) => root.querySelector(sel);
const themeRoot = document.documentElement;
  const chatbotRoot = $('.cbt'); /*only run in chatbot*/
   /* ==========================
   * Chatbot
   * ========================== */
 const chatEl     = $('#cbtChat');
  const form       = $('#cbtComposer');
  const textarea   = $('#cbtMessage');
  const sendBtn    = $('#cbtSendBtn');
  const sidebar    = $('#cbtSidebar');
  const menuBtn    = $('#cbtMenuBtn');
  const themeBtn   = $('#cbtThemeToggle');
  const fileInput  = $('#cbtFileInput');
  const filePreview= $('#cbtFilePreview');

  let sessionId = null;

  // create a session once per page load
  async function startSession() {
       if (!chatbotRoot) return;
    try {
      const res = await fetch('/api/chat/session', { method: 'POST' });
      const data = await res.json();
      sessionId = data.session_id;
    } catch (err) {
      console.error('could not create session', err);
    }
  }

  // sidebar toggle
  menuBtn?.addEventListener('click', () => sidebar?.classList.toggle('open'));

  // theme toggle
  themeBtn?.addEventListener('click', () => {
    const isDark = root.classList.toggle('cbt--dark');
    themeBtn.setAttribute('aria-pressed', String(isDark));
  });

  // autoresize textarea
  const autoGrow = () => {
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, window.innerHeight * 0.4) + 'px';
  };
  textarea?.addEventListener('input', autoGrow);
  window.addEventListener('resize', autoGrow);

  // file preview
  fileInput?.addEventListener('change', () => {
    if (!fileInput.files?.length) {
      filePreview.hidden = true;
      filePreview.textContent = '';
      return;
    }
    const files = [...fileInput.files].map(f => `${f.name} (${Math.round(f.size / 1024)} KB)`);
    filePreview.hidden = false;
    filePreview.textContent = 'attached: ' + files.join(', ');
  });

  // helpers
  const escapeHTML = (s) =>
    s.replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));

  const addMessage = (role, text) => {
    const wrap = document.createElement('div');
    wrap.className = `msg msg--${role === 'user' ? 'user' : 'ai'}`;

    const avatar = document.createElement('div');
    avatar.className = 'msg__avatar';
    avatar.textContent = role === 'user' ? '🧑' : '🤖';

    const bubble = document.createElement('div');
    bubble.className = 'msg__bubble';
    bubble.innerHTML = `<p>${text}</p>`;

    wrap.append(avatar, bubble);
    chatEl.appendChild(wrap);
    chatEl.scrollTop = chatEl.scrollHeight;
  };

  const showTyping = () => {
    if ($('#cbt-typing')) return;
    const row = document.createElement('div');
    row.id = 'cbt-typing';
    row.className = 'msg msg--ai';
    row.innerHTML = `
      <div class="msg__avatar">🤖</div>
      <div class="msg__bubble">
        <span class="typing"><span></span><span></span><span></span></span>
      </div>`;
    chatEl.appendChild(row);
    chatEl.scrollTop = chatEl.scrollHeight;
  };

  const hideTyping = () => {
    const row = $('#cbt-typing');
    row?.parentElement?.removeChild(row);
  };

  // submit handler
  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = textarea.value.trim();
    // nway
    if (!text || !sessionId) return;
 if (!sessionId) {                // <-- added
    await startSession();
    if (!sessionId) return;        // bail if still no session
  }
    addMessage('user', escapeHTML(text));
    textarea.value = '';
    if (fileInput) fileInput.value = '';
    filePreview.hidden = true;
    autoGrow();
    showTyping();

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: text })
      });
      if (!res.ok) throw new Error('bad response');
      const data = await res.json();
      hideTyping();
      addMessage('ai', escapeHTML(data.reply || 'ok!'));
    } catch (err) {
      console.error(err);
      hideTyping();
      addMessage('ai', '⚠️ couldn’t reach the server.');
    }
  });

  // Enter = send, Shift+Enter = newline
  textarea?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendBtn?.click();
    }
  });

  const PHASE_MAP = {
    NEW_MOON: 'New Moon',
    WAXING_CRESCENT: 'Waxing Crescent',
    FIRST_QUARTER: 'First Quarter',
    WAXING_GIBBOUS: 'Waxing Gibbous',
    FULL_MOON: 'Full Moon',
    WANING_GIBBOUS: 'Waning Gibbous',
    LAST_QUARTER: 'Last Quarter',
    THIRD_QUARTER: 'Last Quarter', // alias
    WANING_CRESCENT: 'Waning Crescent',
  };

  const PHASE_EMOJI = {
    'New Moon': '🌑',
    'Waxing Crescent': '🌒',
    'First Quarter': '🌓',
    'Waxing Gibbous': '🌔',
    'Full Moon': '🌕',
    'Waning Gibbous': '🌖',
    'Last Quarter': '🌗',
    'Waning Crescent': '🌘',
  };

  const normalizePhase = (raw) => {
    if (!raw) return 'Unknown';
    const key = String(raw).trim().toUpperCase().replace(/\s+/g, '_');
    return PHASE_MAP[key] || String(raw);
  };

  const getMoonEmoji = (phase) => PHASE_EMOJI[normalizePhase(phase)] || '🌙';

  /* ==========================
   * Sidebar
   * ========================== */

  const initSidebar = () => {
    const sidebar = $('#sidebar');
    const hamburger = $('.hamburger');
    if (sidebar && hamburger) {
      hamburger.addEventListener('click', () => sidebar.classList.toggle('open'));
    }
  };

  /* ==========================
   * Plants
   * ========================== */

  const loadPlants = async () => {
    const res = await fetch('/static/data/indoor_plants.json', { cache: 'no-store' });
    if (!res.ok) throw new Error('/static/data/indoor_plants.json not found');
    return res.json();
  };

  // quick, simple moon phase guesser (calendar-day based heuristic)
  const getMoonPhase = (date) => {
    const day = date.getDate();
    const d = day % 29.53;
    if (d < 1) return 'New Moon';
    if (d < 7) return 'Waxing Crescent Moon';
    if (d < 10) return 'First Quarter';
    if (d < 14) return 'Waxing Gibbous Moon';
    if (d < 16) return 'Full Moon';
    if (d < 22) return 'Waning Gibbous Moon';
    if (d < 25) return 'Last Quarter';
    return 'Waning Crescent Moon';
  };

  // cache plants after first load
let PLANTS = null;

async function ensurePlants() {
  if (PLANTS) return PLANTS;
  const res = await fetch('/static/data/indoor_plants.json', { cache: 'no-store' });
  if (!res.ok) throw new Error('/static/data/indoor_plants.json not found');
  PLANTS = await res.json();
  return PLANTS;
}

function phaseKey(label) {
  // normalize flexible labels like "Waning Gibbous Moon"
  const p = String(label || '').toLowerCase().replace(/moon/g, '').trim();
  if (p.includes('new')) return 'new';
  if (p.includes('waxing crescent')) return 'waxing crescent';
  if (p.includes('first') || p === 'first quarter') return 'first quarter';
  if (p.includes('waxing gibbous')) return 'waxing gibbous';
  if (p.includes('full')) return 'full';
  if (p.includes('waning gibbous')) return 'waning gibbous';
  if (p.includes('last') || p.includes('third') || p === 'last quarter') return 'last quarter';
  if (p.includes('waning crescent')) return 'waning crescent';
  return p;
}

function bucketByPhase(plants, phaseLabel, typeFilter = null) {
  const key = phaseKey(phaseLabel);
  const grow = [], harvest = [], rest = [];

  for (const p of plants) {
    if (typeFilter === 'Edible' && !p.edible) continue;
    if (typeFilter === 'Ornamental' && p.edible) continue;

    const mp = p.moon_phase || {};
    const name = p.plant || p.name || 'Unknown plant';

    if (mp.growing && phaseKey(mp.growing) === key)    grow.push(name);
    if (mp.harvesting && phaseKey(mp.harvesting) === key) harvest.push(name);
    if (mp.resting && phaseKey(mp.resting) === key)    rest.push(name);
  }

  return { grow, harvest, rest };
}

function renderBuckets({ grow, harvest, rest }) {
  const growList = document.getElementById('growList');
  const harvestList = document.getElementById('harvestList');
  const restList = document.getElementById('restList');
  const emptyMsg = document.getElementById('recoEmpty');

  const fill = (ul, arr, emptyLabel) => {
    if (!ul) return;
    ul.innerHTML = '';
    if (!arr.length) {
      const li = document.createElement('li');
      li.textContent = emptyLabel;
      li.setAttribute('aria-disabled', 'true');
      ul.appendChild(li);
      return;
    }
    for (const name of arr) {
      const li = document.createElement('li');
      li.textContent = name;
      ul.appendChild(li);
    }
  };

  fill(growList, grow, 'No suitable plants to grow.');
  fill(harvestList, harvest, 'No plants to harvest.');
  fill(restList, rest, 'No plants resting on this phase.');

  const nothing = !grow.length && !harvest.length && !rest.length;
  if (emptyMsg) emptyMsg.style.display = nothing ? 'block' : 'none';
}


  const recommendPlants = async () => {
  const dateEl = $('#date');                 // keep using #date (not #datePicker)
  const typeEl = $('#plantType');
  const phaseEl = $('#phaseOutput');

  if (!dateEl || !typeEl || !phaseEl) {
    console.warn('recommendPlants(): required elements missing');
    return;
  }

  const dateInput = dateEl.value;
  if (!dateInput) { alert('Please select a date!'); return; }

  const date = new Date(dateInput);

  // Your quick heuristic; keep as-is or replace with /moon?date=...
  const phaseLabel = getMoonPhase(date);
  phaseEl.textContent = `🌙 ${phaseLabel}`;

  try {
    const plants = await ensurePlants();
    const typeFilter = typeEl.value; // "Edible" | "Ornamental" | ""

    const buckets = bucketByPhase(plants, phaseLabel, typeFilter || null);
    renderBuckets(buckets);
  } catch (e) {
    console.error(e);
    const outEl = $('#suggestionOutput');
    if (outEl) outEl.textContent = 'Could not load plant suggestions.';
  }
};

document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('getRecommendations');
  if (btn) {
    btn.addEventListener('click', async () => {
      // grab user inputs
      const dateStr = document.getElementById('datePicker')?.value;
      const typeFilter = document.getElementById('plantType')?.value; // "edible" | "ornamental" | ""

      // call your API to get the phase for that date
      let phaseLabel = null;
      try {
        const res = await fetch(`/moon?date=${encodeURIComponent(dateStr)}`);
        const data = await res.json();
        phaseLabel = data.phase;
      } catch (e) {
        console.error('Could not fetch moon phase:', e);
      }

      // now split into buckets
      const buckets = bucketByPhase(plants, phaseLabel, typeFilter || null);
      renderBuckets(buckets);
    });
  }
});



  // make callable from buttons
  window.recommendPlants = recommendPlants;

  /* ==========================
   * Moon (/moon endpoint)
   * ========================== */

  const updateMoonUI = (phaseRaw, illuminationRaw) => {
    const phase = normalizePhase(phaseRaw);
    const illumination = Math.max(0, Math.min(100, Number(illuminationRaw ?? 0)));

    const bar  = $('#todayMoonBar');
    const txt  = $('#todayMoonText');
    const chip = $('#moonChip'); // optional

    if (bar)  bar.style.width = `${illumination}%`;
    if (txt)  txt.textContent = `${getMoonEmoji(phase)} ${illumination}% - ${phase}`;
    if (chip) chip.textContent = `${getMoonEmoji(phase)} ${illumination}% • ${phase}`;
  };

  const showTodayMoonPhase = async () => {
    try {
      const res = await fetch('/moon', { cache: 'no-store' });
      if (!res.ok) throw new Error(`/moon returned ${res.status}`);
      const data = await res.json();
      updateMoonUI(data.phase ?? data.moon_phase, data.illumination ?? data.moon_illumination);
    } catch (err) {
      console.error('[moon] error:', err);
      const txt = $('#todayMoonText');
      if (txt) txt.textContent = '⚠️ Could not load moon data';
    }
  };

  /* ==========================
   * Weather chip (safe)
   * ========================== */

  const weatherCodeToText = (code) => {
    const map = {
      0: 'Clear', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
      45: 'Fog', 48: 'Depositing rime fog',
      51: 'Light drizzle', 53: 'Drizzle', 55: 'Dense drizzle',
      61: 'Light rain', 63: 'Rain', 65: 'Heavy rain',
      71: 'Light snow', 73: 'Snow', 75: 'Heavy snow',
      80: 'Rain showers', 81: 'Showers', 82: 'Heavy showers',
      95: 'Thunderstorm', 96: 'Thunder w/ hail', 99: 'Severe hail',
    };
    return map[code] || 'Weather';
  };

  const showWeather = async () => {
    const chip = $('#weatherChip');
    if (!chip) return;

    if (!('geolocation' in navigator)) {
      chip.textContent = '⛅ Geolocation unavailable';
      return;
    }

    navigator.geolocation.getCurrentPosition(async ({ coords }) => {
      try {
        const r = await fetch(`/weather?lat=${coords.latitude}&lon=${coords.longitude}`);
        if (!r.ok) throw new Error('weather ' + r.status);

        const w = await r.json();
        const city = w.name ?? '—';
        const temp = Math.round(w?.main?.temp ?? 0);
        const icon = w?.weather?.[0]?.icon ?? '01d';
        const desc = w?.weather?.[0]?.main ?? 'Weather';

        chip.innerHTML = `
          <img src="https://openweathermap.org/img/wn/${icon}.png" alt="${desc}"
               style="width:18px;height:18px;vertical-align:middle"> ${city}: ${temp}°C
        `;
      } catch (e) {
        console.error('[weather] failed:', e);
        chip.textContent = '⚠️ Weather unavailable';
      }
    }, () => {
      chip.textContent = 'Location denied';
    });
  };
/* Pest Detection*/
analyzeBtn.addEventListener('click', async () => {
  results.innerHTML = `<p>🔍 Uploading and analyzing image...</p>`;

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  try {
    const res = await fetch('/pest-detect', {
      method: 'POST',
      body: formData
    });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const data = await res.json();

    if (data.error) {
      results.innerHTML = `<p>⚠️ ${data.error}</p>`;
      return;
    }

    if (data.detected) {
      results.innerHTML = `
        <h4>Detected Pests</h4>
        <ul>${data.pests.map(p => `<li>${p}</li>`).join('')}</ul>
        <h4>Recommendations</h4>
        <ul>${data.recommendations.map(r => `<li>${r}</li>`).join('')}</ul>
      `;
    } else {
      results.innerHTML = `<p>✅ No pests detected.</p>`;
    }
  } catch (err) {
    console.error(err);
    results.innerHTML = `<p>⚠️ Error analyzing image. Try again later.</p>`;
  }
});

  /* ==========================
   * Boot
   * ========================== */

  document.addEventListener('DOMContentLoaded', () => {
     startSession().then(() => {
    initSidebar();

  
    if ($('#todayMoonText') || $('#moonChip')) {
      showTodayMoonPhase();
    }

    if ($('#weatherChip')) {
      showWeather();
    }
  });
});
})();

