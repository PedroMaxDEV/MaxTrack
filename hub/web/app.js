'use strict';
const el = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const token = params.get('chave');
const android = window.MaxGpsAndroid;
const canvas = el('map'), ctx = canvas.getContext('2d');
const demoRoads = {
  name: 'Circuito de demonstração', nodes: [[0,300],[0,0],[320,0],[320,-280],[690,-280],[690,0],[690,300],[320,300],[320,70],[32,-220],[140,-380],[430,-380]],
  roads: [[0,1,0],[1,2,0],[2,3,0],[3,4,0],[4,5,0],[5,6,0],[6,7,0],[7,0,0],[2,5,0],[7,8,0],[8,2,0],[1,9,0],[9,10,0],[10,11,0],[11,3,0]]
};
const alertTypes = {radar: ['Radar', 'R'], police: ['Fiscalização cadastrada', 'F'], bump: ['Quebra-molas', 'Q']};
const demoAlerts = [
  {id:'demo-radar',type:'radar',x:0,z:140,heading:0},
  {id:'demo-bump',type:'bump',x:190,z:0,heading:-.25},
  {id:'demo-police',type:'police',x:320,z:-145,heading:0}
];
let alertState = null, seenAlertRevision = -1, alertPending = false;
const announcedAlerts = new Set();
let truck = null, graph = null, revision = -1, demo = params.has('demo'), demoStarted = performance.now();
let route = null, progress = 0, announced = new Set(), trail = [];
let center = [0,0], zoom = .67, follow = true, pointer = null, selecting = false;
let browserVoices = [], pcVoices = [], voiceGeneration = 0, lastSpeedAlert = 0, warned = false;
let lastDistanceCheckpoint = null;
let projected = {width: 0, height: 0};
const format = (number, digits = 0) => number.toLocaleString('pt-BR', {maximumFractionDigits: digits});
const valid = value => Number.isFinite(value) && value >= 0;
const distance = (a,b) => Math.hypot(a[0]-b[0], a[1]-b[1]);
const localSave = (name, value) => { try { localStorage.setItem(name, value); } catch {} };
const localLoad = (name, fallback) => { try { return localStorage.getItem(name) ?? fallback; } catch { return fallback; } };
const api = (path, options = {}) => fetch(path, {cache:'no-store', ...options,
    headers:{...(options.headers || {}), ...(token ? {'X-MaxGPS-Key':token} : {})}, signal:AbortSignal.timeout(6000)});
el('connect').hidden = !android;
el('connect').onclick = () => android.configure();
if (!android && !token) el('status').textContent = 'Abra o endereço exibido no Hub';

function loadGraph(data) {
  graph = data;
  route = null;
  selecting = false;
  el('clear').disabled = true;
  el('stop-selection').disabled = !data;
  el('stop-selection').setAttribute('aria-pressed', false);
  if (!data) return;
  const adjacency = Array.from(data.nodes, () => []);
  for (const [from,to,oneWay] of data.roads) {
    adjacency[from].push(to);
    if (!oneWay) adjacency[to].push(from);
  }
  graph = {...data, adjacency};
  if (!truck) center = data.nodes[0].slice(0,2);
}

const alertEnabled = el('include-alerts');
alertEnabled.checked = localLoad('road-alerts-enabled','true') === 'true';
alertEnabled.onchange = () => {
  localSave('road-alerts-enabled', String(alertEnabled.checked));
  if (!alertEnabled.checked) announcedAlerts.clear();
  updateRoadAlert();
  renderMap();
};
const activeAlerts = () => demo ? demoAlerts : alertState?.points ?? [];

function showAlertState(state) {
  if (alertState?.scope !== state.scope) announcedAlerts.clear();
  alertState = state;
  const points = state.points.filter(point => !point.id.startsWith('map-'));
  el('alert-scope').textContent = state.scope === 'default' ?
    'Sem mapa importado, as marcações ficam numa lista comum. Desative os alertas se trocar de mapa.' :
    'Marcações pessoais e pontos importados deste mapa.';
  const items = points.map(point => {
    const row = document.createElement('li');
    row.textContent = alertTypes[point.type][0] + ' · X ' + Math.round(point.x) + ' / Z ' + Math.round(point.z);
    const remove = document.createElement('button');
    remove.textContent = 'Remover';
    remove.onclick = () => changeAlert({action:'delete',id:point.id});
    row.append(remove);
    return row;
  });
  el('saved-alerts').replaceChildren(...items);
}

async function changeAlert(command) {
  if (!alertState || alertPending || demo) return;
  alertPending = true;
  const body = JSON.stringify({...command, scope:alertState.scope});
  if (android?.alertCommand) {
    android.alertCommand(body);
    return;
  }
  try {
    const response = await api('/alertas',{method:'POST',headers:{'Content-Type':'application/json'},body});
    if (!response.ok) throw Error();
    finishAlert(await response.json());
  } catch { finishAlert(null); }
}

function finishAlert(answer) {
  alertPending = false;
  el('alert-feedback').textContent = answer?.notice || 'O Hub não recebeu a marcação.';
}
window.maxAlertResponse = raw => {
  try { finishAlert(JSON.parse(raw)); } catch { finishAlert(null); }
};
el('mark-alert').onclick = () => changeAlert({action:'add',type:el('alert-type').value});

function updateRoadAlert() {
  const box = el('road-alert');
  el('mark-alert').disabled = !truck || !alertState || demo || alertPending;
  box.hidden = true;
  if (!truck || !alertEnabled.checked || truck.paused || truck.speed < 1) return false;
  const angle = truck.heading * 2 * Math.PI;
  const fx = -Math.sin(angle), fz = -Math.cos(angle);
  const range = Math.max(80, Math.min(300,25 + truck.speed*8));
  let next = null;
  for (const point of activeAlerts()) {
    const px = point.x-truck.x, pz = point.z-truck.z;
    const meters = Math.hypot(px,pz);
    if (meters > 450) announcedAlerts.delete(point.id);
    const ahead = px*fx+pz*fz;
    const lateral = Math.abs(px*fz-pz*fx);
    if (ahead <= 3 || meters > range || lateral > 32) continue;
    if (Number.isFinite(point.heading) && Math.cos((point.heading-truck.heading)*2*Math.PI) < .45) continue;
    if (!next || meters < next.meters) next = {point, meters};
  }
  if (!next) return false;
  const {point, meters} = next;
  const label = alertTypes[point.type][0];
  box.textContent = label + ' à frente · ' + Math.max(5, Math.round(meters)) + ' m no mapa';
  box.hidden = false;
  if (!announcedAlerts.has(point.id)) {
    announcedAlerts.add(point.id);
    speak(label + ' à frente.');
  }
  return true;
}

function nearest(point, maxDistance) {
  let index = -1;
  graph.nodes.forEach((node, i) => {
    const d = distance(node,point);
    if (d <= maxDistance) { index = i; maxDistance = d; }
  });
  return index;
}

class MinHeap {
  constructor() { this.items = []; }
  push(item) {
    let index = this.items.length;
    while (index > 0) {
      const parent = (index - 1) >> 1;
      if (this.items[parent][0] <= item[0]) break;
      this.items[index] = this.items[parent];
      index = parent;
    }
    this.items[index] = item;
  }
  pop() {
    const result = this.items[0], last = this.items.pop();
    if (this.items.length) {
      let index = 0;
      while (2 * index + 1 < this.items.length) {
        let child = 2 * index + 1;
        if (child + 1 < this.items.length && this.items[child + 1][0] < this.items[child][0]) child++;
        if (this.items[child][0] >= last[0]) break;
        this.items[index] = this.items[child];
        index = child;
      }
      this.items[index] = last;
    }
    return result;
  }
}

function plan(destination) {
  const start = nearest([truck.x,truck.z], 250);
  if (start < 0 || destination < 0 || start === destination) return null;
  const {nodes, adjacency} = graph;
  const lengths = new Float64Array(nodes.length).fill(Infinity);
  const parents = new Int32Array(nodes.length).fill(-1);
  const heap = new MinHeap();
  lengths[start] = 0;
  heap.push([distance(nodes[start],nodes[destination]), start, 0]);
  while (heap.items.length) {
    const [, current, priorLength] = heap.pop();
    if (priorLength !== lengths[current]) continue;
    if (current === destination) break;
    for (const next of adjacency[current]) {
      const length = priorLength + distance(nodes[current],nodes[next]);
      if (length >= lengths[next]) continue;
      lengths[next] = length;
      parents[next] = current;
      heap.push([length + distance(nodes[next],nodes[destination]), next, length]);
    }
  }
  if (parents[destination] < 0) return null;
  const points = [];
  for (let i = destination; i >= 0; i = parents[i]) points.push(nodes[i]);
  points.reverse();
  const steps = [], offsets = [0];
  points.slice(1).forEach((point,i) => offsets.push(offsets[i]+distance(points[i],point)));
  for (let i = 1; i < points.length - 1; i++) {
    const a = points[i-1], b = points[i], c = points[i+1];
    const angle = Math.atan2((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]),
                            (b[0]-a[0])*(c[0]-b[0])+(b[1]-a[1])*(c[1]-b[1]));
    if (Math.abs(angle) > .55) steps.push([offsets[i], angle > 0 ? 'Vire à direita' : 'Vire à esquerda']);
  }
  steps.push([offsets.at(-1), 'Destino à frente']);
  return {points, offsets, steps};
}

function renderMap() {
  const {width,height} = canvas.getBoundingClientRect();
  if (!width || !height) return;
  const dpr = Math.min(devicePixelRatio || 1, 2);
  if (canvas.width !== Math.round(width*dpr) || canvas.height !== Math.round(height*dpr)) {
    canvas.width = Math.round(width*dpr); canvas.height = Math.round(height*dpr);
  }
  projected = {width,height};
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.fillStyle='#101b20'; ctx.fillRect(0,0,width,height);
  if (follow && truck) center = [truck.x,truck.z];
  const xy = p => [width/2 + (p[0]-center[0])*zoom, height*.53 + (p[1]-center[1])*zoom];
  ctx.strokeStyle='#1e3037'; ctx.lineWidth=1; ctx.beginPath();
  const [sx,sy] = xy([0,0]), grid = 64;
  for (let x = sx%grid; x < width; x += grid) { ctx.moveTo(x,0);ctx.lineTo(x,height); }
  for (let y = sy%grid; y < height; y += grid) { ctx.moveTo(0,y);ctx.lineTo(width,y); }
  ctx.stroke();
  const path = (points, color, width) => {
    ctx.beginPath(); ctx.lineJoin='round';ctx.lineCap='round';ctx.lineWidth=width;ctx.strokeStyle=color;
    points.forEach((p,i) => i ? ctx.lineTo(...xy(p)) : ctx.moveTo(...xy(p)));
    ctx.stroke();
  };
  if (graph) {
    ctx.beginPath(); ctx.strokeStyle='#496069';ctx.lineWidth=3;
    const left = center[0]-width/(2*zoom), right = left+width/zoom;
    const top = center[1]-height*.53/zoom, bottom = top+height/zoom;
    for (const [i,j] of graph.roads) {
      const a = graph.nodes[i], b = graph.nodes[j];
      if (Math.max(a[0],b[0]) < left || Math.min(a[0],b[0]) > right ||
          Math.max(a[1],b[1]) < top || Math.min(a[1],b[1]) > bottom) continue;
      ctx.moveTo(...xy(a)); ctx.lineTo(...xy(b));
    }
    ctx.stroke();
  }
  path(trail,'#4ba5c4',3);
  if (route) {
    path(route.points,'#b5f45b',5);
    const [x,y] = xy(route.points.at(-1));
    ctx.fillStyle='#b5f45b'; ctx.beginPath();ctx.arc(x,y,6,0,Math.PI*2);ctx.fill();
  }
  if (alertEnabled.checked) for (const point of activeAlerts()) {
    const [x,y] = xy([point.x,point.z]);
    if (x < 0 || y < 0 || x > width || y > height) continue;
    ctx.fillStyle = '#f4b65f';ctx.beginPath();ctx.arc(x,y,9,0,Math.PI*2);ctx.fill();
    ctx.fillStyle='#23180a';ctx.font='bold 10px system-ui';ctx.textAlign='center';ctx.textBaseline='middle';
    ctx.fillText(alertTypes[point.type][1],x,y);
  }
  if (!truck) return;
  const [x,y] = xy([truck.x,truck.z]);
  ctx.save();ctx.translate(x,y);ctx.rotate(-truck.heading*2*Math.PI);
  ctx.strokeStyle='#0d141a';ctx.lineWidth=3;ctx.fillStyle='#ffffff';
  ctx.beginPath();ctx.moveTo(0,-12);ctx.lineTo(9,9);ctx.lineTo(0,5);ctx.lineTo(-9,9);ctx.closePath();ctx.fill();ctx.stroke();ctx.restore();
}

function setZoom(factor) { zoom = Math.max(.035,Math.min(6,zoom*factor)); renderMap(); }
el('zoom-in').onclick = () => setZoom(1.4);
el('zoom-out').onclick = () => setZoom(1/1.4);
el('center').onclick = () => { follow = true; renderMap(); };
canvas.addEventListener('wheel', event => { event.preventDefault(); setZoom(event.deltaY < 0 ? 1.2 : 1/1.2); }, {passive:false});
canvas.onpointerdown = event => {
  canvas.setPointerCapture(event.pointerId);
  pointer = {id:event.pointerId,x:event.clientX,y:event.clientY,origin:center.slice(),dragged:false};
};
canvas.onpointermove = event => {
  if (!pointer || event.pointerId !== pointer.id) return;
  const dx = event.clientX-pointer.x, dy = event.clientY-pointer.y;
  if (Math.hypot(dx,dy) > 6) pointer.dragged = true;
  if (!pointer.dragged) return;
  center = [pointer.origin[0]-dx/zoom,pointer.origin[1]-dy/zoom];
  follow = false;
  renderMap();
};
canvas.onpointercancel = () => { pointer = null; };
canvas.onpointerup = event => {
  const tap = pointer && !pointer.dragged;
  pointer = null;
  if (!tap || !selecting || !graph || !truck) return;
  const rect = canvas.getBoundingClientRect();
  const destination = [center[0]+(event.clientX-rect.left-projected.width/2)/zoom,
                       center[1]+(event.clientY-rect.top-projected.height*.53)/zoom];
  const proposed = plan(nearest(destination, Math.min(400,32/zoom)));
  if (!proposed) {
    el('instruction').textContent = 'Sem rota para esse ponto';
    el('map-help').textContent = 'Toque em outra estrada conectada ao caminhão.';
    return;
  }
  route = proposed; progress = 0; announced = new Set();
  selecting = false; follow = true;
  el('stop-selection').setAttribute('aria-pressed', false);
  el('clear').disabled = false;
  drawNavigation();
  renderMap();
};
el('stop-selection').onclick = () => {
  selecting = !selecting;
  el('stop-selection').setAttribute('aria-pressed', selecting);
  drawNavigation();
};
el('clear').onclick = () => { route = null; el('clear').disabled = true; drawNavigation(); renderMap(); };
new ResizeObserver(renderMap).observe(canvas);

function drawNavigation() {
  el('map-name').textContent = graph?.name ?? 'Percurso ao vivo';
  el('stop-selection').disabled = !graph || !truck;
  if (selecting || !truck || !route) {
    el('instruction').textContent = selecting && truck ? 'Toque numa estrada para traçar a rota' : !truck ? 'Aguardando o caminhão' : 'Acompanhando o caminhão';
    el('map-help').textContent = !truck ? 'Abra o ETS2 no PC e entre na cabine.' :
      graph ? 'Arraste o mapa e use os botões para ajustar o zoom.' : 'Importe um mapa rodoviário pelo Max Hub para traçar rotas.';
    return;
  }
  const {points, offsets, steps} = route;
  let closest = Infinity, along = 0;
  points.slice(1).forEach((point,i) => {
    if (offsets[i+1] < progress - 50) return;
    const prior = points[i], dx = point[0]-prior[0], dz = point[1]-prior[1];
    const ratio = Math.max(0,Math.min(1,((truck.x-prior[0])*dx+(truck.z-prior[1])*dz)/(dx*dx+dz*dz)));
    const next = Math.hypot(truck.x-prior[0]-ratio*dx,truck.z-prior[1]-ratio*dz);
    if (next < closest) { closest = next; along = offsets[i]+ratio*(offsets[i+1]-offsets[i]); }
  });
  if (closest > 95) {
    el('instruction').textContent = 'Fora da rota';
    el('map-help').textContent = 'Escolha o destino novamente para recalcular.';
    return;
  }
  progress = Math.max(progress,along);
  const index = steps.findIndex(([offset]) => offset >= progress + 8);
  if (index < 0) {
    el('instruction').textContent = 'Destino alcançado';el('map-help').textContent = '';
    if (!announced.has('arrival') && !truck.paused) { announced.add('arrival'); speak('Você chegou ao destino.'); }
    return;
  }
  const [offset, instruction] = steps[index];
  const meters = Math.round(offset-progress);
  el('instruction').textContent = instruction;
  el('map-help').textContent = `Em ${format(meters)} m no mapa`;
  if (meters <= Math.max(40,Math.abs(truck.speed)*5) && !announced.has(index) && !truck.paused && el('road-alert').hidden) {
    announced.add(index);
    speak(`${instruction} em ${Math.max(10,Math.round(meters/10)*10)} metros.`);
  }
}

function update(data) {
  truck = data;
  const hazardAhead = updateRoadAlert();
  el('status').dataset.live = Boolean(truck);
  el('status').textContent = demo ? 'Demonstração' : truck ? (truck.paused ? 'ETS2 pausado' : '● ETS2 ao vivo') :
    token || android ? 'Aguardando o ETS2' : 'Abra o endereço exibido no Hub';
  const kmh = value => valid(value) ? format(value*3.6) : '—';
  el('speed').textContent = truck && truck.speed !== -1 ? kmh(Math.abs(truck.speed)) : '—';
  el('limit').textContent = truck?.limit > 0 ? kmh(truck.limit) : '—';
  el('distance').textContent = truck?.distance > 0 ? `${format(truck.distance/1000,1)} km` : '—';
  const mins = Math.round((truck?.seconds || 0)/60);
  el('eta').textContent = mins > 0 ? `${Math.floor(mins/60)}h ${mins%60}m` : '—';
  el('fuel').textContent = valid(truck?.fuel) ? `${format(truck.fuel)}${truck.fuelCapacity > 0 ? ' / '+format(truck.fuelCapacity) : ''} L` : '—';
  const gear = truck?.gear;
  el('gear').textContent = Number.isFinite(gear) ? `${gear < 0 ? 'R'+Math.abs(gear) : gear || 'N'} · ${valid(truck.rpm) ? format(truck.rpm)+' rpm' : '—'}` : '—';
  el('cruise').textContent = truck?.cruise > 0 ? `${kmh(truck.cruise)} km/h` : '—';
  el('wear').textContent = valid(truck?.wear) ? `${format(truck.wear*100,1)}%` : '—';
  el('destination').textContent = truck?.delivery ? [truck.origin,truck.delivery].filter(Boolean).join(' → ') : 'Sem entrega ativa';
  el('cargo').textContent = [truck?.cargo,truck?.income ? '€ '+format(truck.income) : ''].filter(Boolean).join(' · ') || '—';
  el('truck').textContent = [truck?.truckName, valid(truck?.odometer) ? format(truck.odometer)+' km' : ''].filter(Boolean).join(' · ') || '—';
  if (truck) {
    const point = [truck.x,truck.z];
    if (!trail.length || distance(trail.at(-1),point) >= 3) trail.push(point);
    if (trail.length > 400) trail.shift();
    if (!truck.paused) {
      const over = truck.limit > 0 && Math.abs(truck.speed) - truck.limit > 2.2;
      if (over && !warned && !hazardAhead && Date.now()-lastSpeedAlert > 15000) {
        speak('Atenção. Você está acima do limite de velocidade.');
        lastSpeedAlert = Date.now(); warned = true;
      } else if (!over) warned = false;
      const checkpoint = truck.distance > 0 ? Math.floor(truck.distance/10000) : null;
      if (!hazardAhead && !route && checkpoint > 0 && lastDistanceCheckpoint !== null && checkpoint < lastDistanceCheckpoint)
        speak(`Restam aproximadamente ${Math.round(truck.distance/1000)} quilômetros.`);
      lastDistanceCheckpoint = checkpoint;
    }
  } else {
    lastDistanceCheckpoint = null;
    warned = false;
  }
  drawNavigation(); renderMap();
}

function speak(text, test = false) {
  const output = el('voice-output').value, voice = el('voice-name').value;
  const rate = Number(el('voice-rate').value), pitch = Number(el('voice-pitch').value);
  if (output === 'off') {
    if (test) el('voice-feedback').textContent = 'Selecione uma saída de áudio.';
  } else if (output === 'pc') {
    if (android) { android.speakPc(JSON.stringify({text,voice,rate})); return; }
    api('/voz',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,voice,rate})})
      .then(r => { if (test) el('voice-feedback').textContent = r.ok ? 'Aviso enviado ao PC.' : 'Não foi possível enviar ao PC.'; })
      .catch(() => { if (test) el('voice-feedback').textContent = 'PC indisponível.'; });
  } else if (android) {
    android.speak(text,voice,rate,pitch);
  } else if ('speechSynthesis' in window) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'pt-BR';utterance.rate = rate;utterance.pitch = pitch;
    utterance.voice = browserVoices.find(item => item.name === voice) ||
                      browserVoices.find(item => item.lang.toLowerCase() === 'pt-br') || null;
    speechSynthesis.cancel();
    speechSynthesis.speak(utterance);
  } else if (test) el('voice-feedback').textContent = 'Sem sintetizador de voz neste dispositivo.';
}
async function refreshVoices() {
  const generation = ++voiceGeneration;
  const output = el('voice-output').value;
  let names = [];
  if (output === 'pc') {
    try {
      const response = await api('/vozes');
      if (response.ok) pcVoices = (await response.json()).voices;
      names = pcVoices;
    } catch {}
  } else if (output === 'local') {
    if (android) { try { names = JSON.parse(android.voices()); } catch {} }
    else if ('speechSynthesis' in window) {
      browserVoices = speechSynthesis.getVoices();
      names = browserVoices.map(voice => voice.name);
    }
  }
  if (generation !== voiceGeneration) return;
  el('voice-name').replaceChildren(new Option('Padrão',''), ...names.map(name => new Option(name,name)));
  const saved = localLoad('voice-'+output,'');
  if (names.includes(saved)) el('voice-name').value = saved;
  el('voice-pitch').disabled = output !== 'local';
}
for (const [id, fallback] of [['voice-output','off'],['voice-rate','1'],['voice-pitch','1']])
  el(id).value = localLoad(id,fallback);
el('voice-output').onchange = () => {
  localSave('voice-output',el('voice-output').value);
  el('voice-feedback').textContent = '';
  if (android) android.stopSpeech();
  else if ('speechSynthesis' in window) speechSynthesis.cancel();
  refreshVoices();
};
el('voice-name').onchange = () => localSave('voice-'+el('voice-output').value,el('voice-name').value);
for (const id of ['voice-rate','voice-pitch']) el(id).onchange = () => localSave(id,el(id).value);
el('test-voice').onclick = () => speak('Max GPS conectado. Em trezentos metros, vire à direita.',true);
if (!android && 'speechSynthesis' in window) speechSynthesis.onvoiceschanged = refreshVoices;
window.refreshMaxGpsVoices = refreshVoices;
refreshVoices();

function demoSample() {
  const cycle = [0,1,2,3,4,5,6,7,0].map(index => demoRoads.nodes[index]);
  const seconds = (performance.now()-demoStarted)/1000;
  const total = cycle.slice(1).reduce((sum,p,i) => sum+distance(p,cycle[i]),0);
  let meters = (seconds*22)%total;
  for (let i=1;i<cycle.length;i++) {
    const a=cycle[i-1],b=cycle[i],length=distance(a,b);
    if (meters <= length) return {x:a[0]+(b[0]-a[0])*meters/length,z:a[1]+(b[1]-a[1])*meters/length,
      speed:22, limit:25, distance:86100-seconds*22%40000, seconds:3900, heading:-Math.atan2(b[0]-a[0],a[1]-b[1])/(2*Math.PI),
      gear:11,rpm:1360,fuel:417,fuelCapacity:640,cruise:22,wear:.028,cargo:'Equipamentos',income:21850,
      truckName:'Caminhão de teste',origin:'Porto',delivery:'Centro de distribuição',odometer:23108};
    meters -= length;
  }
}
el('demo').onclick = () => {
  demo = !demo; demoStarted=performance.now(); revision=-1; trail=[]; follow=true;
  alertState=null; seenAlertRevision=-1; announcedAlerts.clear();
  el('saved-alerts').replaceChildren();
  el('alert-feedback').textContent = '';
  loadGraph(demo ? demoRoads : null);
  el('demo').textContent = demo ? 'Encerrar demonstração' : 'Testar demonstração';
  update(demo ? demoSample() : null);
};
if (demo) {
  loadGraph(demoRoads);
  el('demo').textContent = 'Encerrar demonstração';
}
async function poll() {
  if (demo) update(demoSample());
  else if (token || android) {
    try {
      const response = await api('/telemetria');
      if (!response.ok) throw Error('Servidor indisponível');
      const state = await response.json();
      if (state.features?.gps === false && !demo) {
        if (revision !== -1) { loadGraph(null); revision = -1; }
        update(null);
        el('status').textContent = 'Ative o Max GPS com a chave no Max Hub';
        setTimeout(poll, 1000);
        return;
      }
      if (state.mapRevision !== revision && !demo) {
        alertState=null;
        seenAlertRevision=-1;
        try {
          const map = await api('/mapa');
          if (map.ok && !demo) { loadGraph(await map.json()); revision = state.mapRevision; }
        } catch {}
      }
      if (!demo && Number.isInteger(state.alertRevision) && state.alertRevision !== seenAlertRevision) {
        try {
          const alerts = await api('/alertas');
          if (alerts.ok && !demo) { showAlertState(await alerts.json()); seenAlertRevision = state.alertRevision; }
        } catch {}
      }
      if (!demo) update(state.truck);
    } catch {
      if (!demo) {
        update(null);
        el('status').textContent = 'Hub desconectado';
      }
    }
  } else update(null);
  setTimeout(poll, demo ? 130 : 400);
}
poll();
