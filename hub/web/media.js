'use strict';
(() => {
  const byId = id => document.getElementById(id);
  const native = window.MaxGpsAndroid;
  const key = new URLSearchParams(location.search).get('chave');
  const headers = {'Content-Type':'application/json', ...(key ? {'X-MaxGPS-Key':key} : {})};
  const status = byId('media-status');
  const form = byId('media-search');
  const results = byId('media-results');
  let open = false, request = null, revision = '', timer = null;
  let synchronized = false, refreshing = false;

  function select(media) {
    open = media;
    byId('gps-view').hidden = media;
    byId('media-view').hidden = !media;
    byId('tab-gps').setAttribute('aria-pressed', !media);
    byId('tab-media').setAttribute('aria-pressed', media);
    if (media) refresh();
    else {
      clearTimeout(timer);
      timer = null;
    }
  }

  function draw(state) {
    synchronized = true;
    const signature = JSON.stringify([state.query, state.results]);
    if (signature === revision) return;
    revision = signature;
    results.replaceChildren(...state.results.map((item, i) => {
      const line = document.createElement('li'), button = document.createElement('button');
      button.textContent = (i+1) + '. ' + item.title;
      const channel = document.createElement('small');
      channel.textContent = item.channel;
      button.append(channel);
      button.onclick = () => send({action:'result', index:i+1, query:state.query});
      line.append(button);
      return line;
    }));
  }

  async function refresh() {
    if (refreshing || !open) return;
    refreshing = true;
    if (timer !== null) clearTimeout(timer);
    try {
      const response = await fetch('/multimidia', {headers, cache:'no-store', signal:AbortSignal.timeout(3500)});
      if (!response.ok) throw Error();
      const state = await response.json();
      draw(state);
      if (!request && (status.textContent === 'Abra o Max Hub no PC para conectar.' ||
                       status.textContent === 'Sem conexão com o Hub.')) {
        status.textContent = state.numbered ? 'Conectado. Busque um artista ou fale um comando.' :
          'Conectado. A busca abre no YouTube do PC.';
      }
    } catch {
      synchronized = false;
      if (!request && open) status.textContent = 'Sem conexão com o Hub.';
    }
    refreshing = false;
    if (open) timer = setTimeout(refresh, 1200);
  }

  function complete(ok, notice) {
    request = null;
    status.textContent = notice || (ok ? 'Comando enviado.' : 'Não foi possível enviar o comando.');
    if (open) refresh();
  }

  async function send(command) {
    if (request) return;
    if (!synchronized && !native && !key) {
      status.textContent = 'Abra o endereço de pareamento exibido no Hub.';
      return;
    }
    request = command;
    status.textContent = command.action === 'search' ? 'Buscando…' : 'Enviando comando…';
    if (native?.mediaCommand) {
      native.mediaCommand(JSON.stringify(command));
      return;
    }
    try {
      const response = await fetch('/multimidia', {method:'POST', headers, body:JSON.stringify(command),
        signal:AbortSignal.timeout(8500)});
      if (!response.ok) throw Error();
      const answer = await response.json();
      complete(answer.ok, answer.notice);
    } catch {
      complete(false, 'Sem conexão com o Hub.');
    }
  }

  window.maxMediaResponse = raw => {
    try { const result = JSON.parse(raw); complete(result.ok, result.notice); }
    catch { complete(false, 'Sem conexão com o Hub.'); }
  };
  window.maxMediaVoice = phrase => { if (phrase) send({action:'voice', phrase}); };
  byId('tab-gps').onclick = () => select(false);
  byId('tab-media').onclick = () => select(true);
  for (const button of document.querySelectorAll('[data-media]'))
    button.onclick = () => send({action:button.dataset.media});
  for (const button of document.querySelectorAll('[data-app]'))
    button.onclick = () => send({action:'open', app:button.dataset.app});
  form.onsubmit = event => {
    event.preventDefault();
    send({action:'search', query:byId('media-query').value.trim()});
  };
  const mic = byId('media-mic');
  mic.hidden = !native?.recognizeMedia;
  mic.onclick = () => native.recognizeMedia();
})();
