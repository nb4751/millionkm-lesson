(() => {
  'use strict';
  const menu = document.querySelector('.menu-toggle');
  const sidebar = document.querySelector('.sidebar');
  if (menu && sidebar) {
    menu.addEventListener('click', () => {
      const open = sidebar.classList.toggle('open');
      menu.setAttribute('aria-expanded', String(open));
      menu.setAttribute('aria-label', open ? '메뉴 닫기' : '메뉴 열기');
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') { sidebar.classList.remove('open'); menu.setAttribute('aria-expanded', 'false'); }
    });
    document.addEventListener('click', event => {
      if (!sidebar.contains(event.target) && !menu.contains(event.target)) {
        sidebar.classList.remove('open'); menu.setAttribute('aria-expanded', 'false');
      }
    });
  }

  const durationLabel = seconds => {
    const n = Math.round(Number(seconds));
    if (!Number.isFinite(n) || n < 0) return '미측정';
    if (n < 60) return `${n}초`;
    if (n < 3600) return `${Math.floor(n / 60)}분${n % 60 ? ` ${n % 60}초` : ''}`;
    return `${Math.floor(n / 3600)}시간${n % 3600 >= 60 ? ` ${Math.floor((n % 3600) / 60)}분` : ''}`;
  };
  document.querySelectorAll('[data-duration]').forEach(element => {
    element.textContent = durationLabel(element.dataset.duration);
  });

  document.querySelectorAll('[data-copy]').forEach(button => {
    button.addEventListener('click', async () => {
      const field = document.getElementById(button.dataset.copy);
      if (!field) return;
      try {
        if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(field.value);
        else { field.select(); field.setSelectionRange(0, field.value.length); if (!document.execCommand('copy')) throw new Error('copy'); }
        button.textContent = '복사됨 ✓';
      } catch (_) {
        field.focus(); field.select(); button.textContent = '선택됨 · 직접 복사';
      }
      button.setAttribute('aria-live', 'polite');
    });
  });

  const uploadForm = document.querySelector('[data-upload-form]');
  if (uploadForm) {
    const mapping = uploadForm.querySelector('#id_mapping');
    const advancedSlot = uploadForm.querySelector('[data-mapping-advanced]');
    if (mapping && advancedSlot) {
      const details = document.createElement('details');
      details.className = 'mapping-advanced';
      const summary = document.createElement('summary');
      summary.textContent = '고급 설정 · CSV 열 직접 연결';
      details.appendChild(summary);
      const fieldContainer = mapping.closest('p');
      if (fieldContainer) details.appendChild(fieldContainer);
      else details.appendChild(mapping);
      advancedSlot.appendChild(details);
      let existing = {};
      try { existing = JSON.parse(mapping.value || '{}'); } catch (_) { details.open = true; }
      const selectors = [...uploadForm.querySelectorAll('[data-map-field]')];
      selectors.forEach(select => {
        if (existing[select.dataset.mapField]) select.value = existing[select.dataset.mapField];
        select.addEventListener('change', () => {
          let value = {};
          try { value = JSON.parse(mapping.value || '{}'); } catch (_) { /* replace invalid custom mapping */ }
          selectors.forEach(field => {
            if (field.value) value[field.dataset.mapField] = field.value;
            else delete value[field.dataset.mapField];
          });
          mapping.value = Object.keys(value).length ? JSON.stringify(value) : '';
        });
      });
    }
  }
  document.querySelectorAll('form[enctype="multipart/form-data"]').forEach(form => {
    form.addEventListener('submit', () => {
      const button = form.querySelector('button[type="submit"]');
      if (button) { button.disabled = true; button.textContent = '파일을 분석하고 있어요…'; }
    });
  });
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  const readData = id => {
    const element = document.getElementById(id);
    try { return element ? JSON.parse(element.textContent) : null; } catch (_) { return null; }
  };
  const isNumber = value => value !== null && value !== '' && value !== undefined && Number.isFinite(Number(value));
  const getCanvas = canvas => {
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(rect.width * ratio);
    canvas.height = Math.round(rect.height * ratio);
    const context = canvas.getContext('2d');
    context.scale(ratio, ratio);
    context.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    return { context, width: rect.width, height: rect.height };
  };
  const emptyChart = (context, width, height, message = '시계열 데이터가 없습니다') => {
    context.fillStyle = '#a1ad96'; context.textAlign = 'center';
    context.fillText(message, width / 2, height / 2);
  };
  const grid = (context, left, right, top, bottom, max, min = 0) => {
    context.lineWidth = 1;
    for (let i = 0; i <= 2; i += 1) {
      const y = top + (bottom - top) * i / 2;
      context.strokeStyle = '#eef1e8'; context.beginPath(); context.moveTo(left, y); context.lineTo(right, y); context.stroke();
      context.fillStyle = '#a5af9a'; context.textAlign = 'right';
      context.fillText(String(Math.round(max - (max - min) * i / 2)), left - 7, y + 3);
    }
  };
  function rideChart(canvas, data) {
    const { context:ctx, width, height } = getCanvas(canvas);
    if (!Array.isArray(data) || data.length < 2) return emptyChart(ctx, width, height);
    const samples = data.filter(row => isNumber(row.elapsed_seconds));
    if (samples.length < 2) return emptyChart(ctx, width, height);
    const last = Math.max(...samples.map(row => Number(row.elapsed_seconds)));
    if (!last) return emptyChart(ctx, width, height);
    const left = 42, right = width - 12, top = 13, bottom = height - 24;
    const tracks = [
      { key:'power', color:'#2c8e76', label:'파워 · W', step:100 },
      { key:'heart_rate', color:'#db7982', label:'심박 · bpm', step:50 },
      { key:'cadence', color:'#9c85d4', label:'케이던스 · rpm', step:50 },
    ];
    const trackHeight = (bottom - top) / 3;
    tracks.forEach((track, trackIndex) => {
      const values = samples.filter(row => isNumber(row[track.key]));
      const trackTop = top + trackIndex * trackHeight + 12;
      const trackBottom = top + (trackIndex + 1) * trackHeight - 11;
      ctx.fillStyle = track.color; ctx.textAlign = 'left'; ctx.fillText(track.label, left, trackTop - 6);
      if (!values.length) {
        ctx.fillStyle = '#b0b8a6'; ctx.textAlign = 'center'; ctx.fillText('미측정', (left + right) / 2, (trackTop + trackBottom) / 2 + 3); return;
      }
      const maximum = Math.max(track.step, Math.ceil(Math.max(...values.map(row => Number(row[track.key]))) / track.step) * track.step);
      grid(ctx,left,right,trackTop,trackBottom,maximum);
      ctx.strokeStyle = track.color; ctx.lineWidth = 1.4; ctx.beginPath();
      let previous = null;
      for (const row of samples) {
        if (!isNumber(row[track.key])) { previous = null; continue; }
        const elapsed = Number(row.elapsed_seconds);
        const x = left + (right - left) * elapsed / last;
        const y = trackBottom - (trackBottom - trackTop) * Number(row[track.key]) / maximum;
        if (previous === null || elapsed - previous > 5 || elapsed < previous) ctx.moveTo(x,y);
        else ctx.lineTo(x,y);
        previous = elapsed;
      }
      ctx.stroke();
    });
    for (let i = 0; i <= 4; i += 1) {
      ctx.textAlign = i === 0 ? 'left' : i === 4 ? 'right' : 'center'; ctx.fillStyle = '#9eab92';
      ctx.fillText(durationLabel(last * i / 4), left + (right - left) * i / 4, height - 4);
    }
  }
  function curveChart(canvas, data) {
    const {context:ctx,width,height} = getCanvas(canvas);
    const rows = Object.entries(data || {}).filter(([seconds,value]) => isNumber(value) && Number(seconds) > 0).sort((a,b) => Number(a[0]) - Number(b[0]));
    if (!rows.length) return emptyChart(ctx,width,height,'계산 가능한 파워커브가 없습니다');
    const left=43,right=width-15,top=17,bottom=height-30;
    const maximum = Math.max(100, Math.ceil(Math.max(...rows.map(row=>Number(row[1]))) / 100) * 100);
    grid(ctx,left,right,top,bottom,maximum);
    const firstLog=Math.log(Number(rows[0][0])),lastLog=Math.log(Number(rows[rows.length-1][0]));
    const xFor = seconds => left + (right-left)*(lastLog===firstLog ? .5 : (Math.log(Number(seconds))-firstLog)/(lastLog-firstLog));
    ctx.beginPath(); ctx.strokeStyle='#4c9068';ctx.lineWidth=2;
    rows.forEach(([seconds,value],index)=>{const x=xFor(seconds),y=bottom-(bottom-top)*Number(value)/maximum;index?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();
    rows.forEach(([seconds,value],index)=>{
      const x=xFor(seconds),y=bottom-(bottom-top)*Number(value)/maximum;
      ctx.beginPath();ctx.arc(x,y,3,0,Math.PI*2);ctx.fillStyle='#4c9068';ctx.fill();
      if (rows.length <= 6 || index % 2===0 || index===rows.length-1) {
        ctx.textAlign=index===0?'left':index===rows.length-1?'right':'center';ctx.fillStyle='#a2ae96';ctx.fillText(durationLabel(seconds),x,height-7);
      }
    });
    ctx.fillStyle='#a2ae96';ctx.textAlign='left';ctx.fillText('W',left,10);
  }
  function loadChart(canvas, data) {
    const {context:ctx,width,height} = getCanvas(canvas);
    if (!Array.isArray(data) || data.length < 2) return emptyChart(ctx,width,height,'훈련부하 추세를 표시할 기록이 부족합니다');
    const tracks=[{key:'ctl',color:'#2c8e76'},{key:'atl',color:'#9c85d4'},{key:'tsb',color:'#dca95f'}];
    const numbers=tracks.flatMap(track=>data.filter(row=>isNumber(row[track.key])).map(row=>Number(row[track.key])));
    if(!numbers.length)return emptyChart(ctx,width,height);
    const left=42,right=width-14,top=15,bottom=height-28;
    const max=Math.max(10,Math.ceil(Math.max(...numbers)/10)*10),min=Math.min(0,Math.floor(Math.min(...numbers)/10)*10);
    grid(ctx,left,right,top,bottom,max,min);
    tracks.forEach(track=>{ctx.beginPath();ctx.strokeStyle=track.color;ctx.lineWidth=1.8;let running=false;data.forEach((row,index)=>{if(!isNumber(row[track.key])){running=false;return;}const x=left+(right-left)*index/(data.length-1),y=bottom-(bottom-top)*(Number(row[track.key])-min)/(max-min);running?ctx.lineTo(x,y):ctx.moveTo(x,y);running=true;});ctx.stroke();});
    [0,Math.floor((data.length-1)/2),data.length-1].forEach((index,position)=>{ctx.fillStyle='#a2ae96';ctx.textAlign=position===0?'left':position===2?'right':'center';ctx.fillText(String(data[index].date || data[index].day || '').slice(5),left+(right-left)*index/(data.length-1),height-6);});
  }
  document.querySelectorAll('canvas[data-chart]').forEach(canvas => {
    const draw = () => {
      const data = readData(canvas.dataset.source);
      if (canvas.dataset.chart==='ride') rideChart(canvas,data);
      else if (canvas.dataset.chart==='curve') curveChart(canvas,data);
      else if (canvas.dataset.chart==='load') loadChart(canvas,data);
    };
    draw();
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(draw).observe(canvas.parentElement);
    else window.addEventListener('resize',draw);
  });
})();
