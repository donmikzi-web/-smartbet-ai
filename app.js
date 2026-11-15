const games=[
{id:1,sport:'Basketball',league:'NBA · REGULAR SEASON',home:'Boston Celtics',away:'Miami Heat',time:'Tonight · 12:30 AM WAT',market:'1st Half Total Points',pick:'Over 109.5',odds:'1.87 (sample)',score:74,reason:'Illustrative estimate only · live pace and lineup data unavailable.'},
{id:2,sport:'Basketball',league:'NBA · REGULAR SEASON',home:'Los Angeles Lakers',away:'Golden State Warriors',time:'Tonight · 3:00 AM WAT',market:'1st Half Total Points',pick:'Over 112.5',odds:'1.91 (sample)',score:68,reason:'Illustrative estimate only · verify team news and market line.'},
{id:3,sport:'Basketball',league:'NCAA · MEN',home:'Duke Blue Devils',away:'North Carolina Tar Heels',time:'Fixture example · time TBC',market:'1st Half Total Points',pick:'Over 69.5',odds:'1.85 (sample)',score:63,reason:'Illustrative college matchup · no verified fixture or team statistics.'},
{id:4,sport:'Basketball',league:'NBA · REGULAR SEASON',home:'Denver Nuggets',away:'Phoenix Suns',time:'Fixture example · time TBC',market:'Full Game Total Points',pick:'Over 224.5',odds:'1.90 (sample)',score:61,reason:'Illustrative estimate only · current odds and injury reports not connected.'},
{id:5,sport:'Football',league:'ENGLISH PREMIER LEAGUE',home:'Arsenal',away:'Chelsea',time:'Fixture example · time TBC',market:'Total Goals',pick:'Over 1.5',odds:'1.32 (sample)',score:79,reason:'Illustrative estimate only · fixture, form and odds are not live-verified.'},
{id:6,sport:'Football',league:'SPANISH LA LIGA',home:'Barcelona',away:'Sevilla',time:'Fixture example · time TBC',market:'Both Teams To Score',pick:'Yes',odds:'1.72 (sample)',score:66,reason:'Illustrative estimate only · no current match data connected.'}
];
let activeFilter='All';let slip=JSON.parse(localStorage.getItem('smartbet-slip')||'[]');
const $=s=>document.querySelector(s);
function renderMatches(target='#match-list'){const list=$(target);if(!list)return;const data=games.filter(g=>activeFilter==='All'||g.sport===activeFilter);list.innerHTML=data.map(g=>`<article class="match-card"><div><div class="league">${g.sport==='Basketball'?'🏀':'⚽'} &nbsp;${g.league}</div><div class="teams">${g.home}<br>${g.away}</div><div class="match-time">${g.time}</div></div><div><div class="market-title">SUGGESTED MARKET</div><div class="market-name">${g.market}</div><div class="market-odds">${g.pick} · ${g.odds}</div></div><div class="confidence"><div class="ring" style="--score:${g.score}%"><span>${g.score}%</span></div><div><strong style="font-size:11px">Model rating</strong><small>Unverified demo</small></div></div><button class="add-btn" data-add="${g.id}" ${slip.some(x=>x.id===g.id)?'disabled':''}>${slip.some(x=>x.id===g.id)?'✓ Added':'+ Add pick'}</button></article>`).join('');list.querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>addPick(+b.dataset.add));}
function save(){localStorage.setItem('smartbet-slip',JSON.stringify(slip));$('#slip-count').textContent=slip.length;$('#pick-total').textContent=slip.length;renderMatches();renderMatches('#prediction-list');renderSlip();}
function addPick(id){if(!slip.some(x=>x.id===id)){slip.push(games.find(g=>g.id===id));save();}}
function renderSlip(){const box=$('#slip-items');if(!box)return;if(!slip.length){box.innerHTML='<div class="empty-state"><div>▤</div><h3>Your slip is empty</h3><p>Go to the dashboard and add a selection to get started.</p></div>';return;}box.innerHTML=slip.map(g=>`<div class="slip-item"><div><strong>${g.home} vs ${g.away}</strong><small>${g.market} · ${g.pick} · ${g.odds}</small></div><button class="remove-btn" data-remove="${g.id}">Remove ×</button></div>`).join('');box.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{slip=slip.filter(x=>x.id!==+b.dataset.remove);save();});}
function showView(name){document.querySelectorAll('.content').forEach(v=>v.classList.add('hidden'));$('#'+name+'-view').classList.remove('hidden');document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b.dataset.view===name));$('#page-name').textContent=name[0].toUpperCase()+name.slice(1);if(name==='predictions')renderMatches('#prediction-list');if(name==='slip')renderSlip();}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>showView(b.dataset.view));document.querySelectorAll('[data-sport]').forEach(b=>b.onclick=()=>{activeFilter=b.dataset.sport;document.querySelectorAll('[data-sport]').forEach(x=>x.classList.toggle('selected',x===b));document.querySelectorAll('.filter').forEach(x=>x.classList.toggle('active',x.dataset.filter===activeFilter));showView('dashboard');renderMatches();});document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{activeFilter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('[data-sport]').forEach(x=>x.classList.toggle('selected',x.dataset.sport===activeFilter));renderMatches();});$('#clear-slip').onclick=()=>{slip=[];save();};$('#copy-slip').onclick=async()=>{const txt=slip.map((g,i)=>`${i+1}. ${g.home} vs ${g.away}\n${g.market}: ${g.pick}\nOdds shown (sample): ${g.odds}`).join('\n\n')||'No selections';try{await navigator.clipboard.writeText(txt);$('#copy-feedback').textContent='Selections copied. Verify every market and price with your bookmaker.';}catch(e){$('#copy-feedback').textContent=txt;}};$('#dismiss-notice').onclick=()=>$('.notice').remove();$('#refresh-btn').onclick=()=>{renderMatches();$('#refresh-btn').textContent='✓ Board refreshed';setTimeout(()=>$('#refresh-btn').textContent='↻ Refresh board',1300);};save();


// Fetch Premier League metadata through the local backend proxy. The API key
// stays on the server and is never exposed to the browser.
const eplButton = document.querySelector('#load-epl-btn');
if (eplButton) eplButton.addEventListener('click', async () => {
  const status = document.querySelector('#epl-api-status');
  const output = document.querySelector('#epl-league-result');
  eplButton.disabled = true;
  eplButton.textContent = 'Loading…';
  status.textContent = 'Requesting API-Sports…';
  output.textContent = '';
  try {
    const response = await fetch('/api/football/leagues?id=39&season=2026');
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    const league = payload.response?.[0];
    if (!league) {
      output.textContent = 'The API returned no league record for ID 39 and season 2026. Check the season availability in your API-Sports plan.';
      status.textContent = 'No league record';
    } else {
      const country = league.country?.name || 'Country unavailable';
      const season = (league.seasons || []).find(x => Number(x.year) === 2026) || (league.seasons || [])[0];
      const coverage = season?.coverage || {};
      const fixtures = coverage.fixtures || {};
      const capability = (label, enabled) => `<span class="coverage-chip ${enabled ? 'available' : 'unavailable'}">${enabled ? '✓' : '—'} ${escapeHtml(label)}</span>`;
      const logo = league.league?.logo ? `<img class="league-logo" src="${escapeHtml(league.league.logo)}" alt="" loading="lazy">` : '';
      const flag = league.country?.flag ? `<img class="country-flag" src="${escapeHtml(league.country.flag)}" alt="" loading="lazy">` : '';
      output.innerHTML = `<div class="league-identity">${logo}<div><strong>${escapeHtml(league.league?.name || 'League')}</strong><div>${flag}${escapeHtml(country)} · ${escapeHtml(league.league?.type || 'Competition')}</div></div></div><div class="league-meta"><span>League ID: <b>${escapeHtml(String(league.league?.id ?? 39))}</b></span><span>Season: <b>${escapeHtml(String(season?.year ?? 'N/A'))}</b></span><span>Dates: <b>${escapeHtml(season ? `${season.start} to ${season.end}` : 'Not supplied')}</b></span><span>Status: <b>${season?.current ? 'Current' : 'Not marked current'}</b></span></div><div class="coverage-title">Provider data coverage</div><div class="coverage-grid">${capability('Fixtures', !!fixtures.events)}${capability('Lineups', !!fixtures.lineups)}${capability('Fixture statistics', !!fixtures.statistics_fixtures)}${capability('Player statistics', !!fixtures.statistics_players)}${capability('Standings', !!coverage.standings)}${capability('Players', !!coverage.players)}${capability('Top scorers', !!coverage.top_scorers)}${capability('Top assists', !!coverage.top_assists)}${capability('Injuries', !!coverage.injuries)}${capability('Predictions', !!coverage.predictions)}${capability('Odds', !!coverage.odds)}</div><p class="coverage-note">Coverage indicates what the API provider makes available for this league/season; it does not mean those datasets have been downloaded yet.</p>`;
      status.textContent = 'Connected · league data received';
    }
  } catch (error) {
    status.textContent = 'Connection not ready';
    output.textContent = error.message + ' — Ensure the backend is running and API_FOOTBALL_KEY is configured.';
  } finally {
    eplButton.disabled = false;
    eplButton.textContent = 'Load league data';
  }
});
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

// SmartBet AI analysis API: manual historical-data ingestion and transparent estimates.
const gameForm = document.querySelector('#game-entry-form');
if (gameForm) gameForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const status = document.querySelector('#game-entry-status');
  const data = Object.fromEntries(new FormData(gameForm).entries());
  ['home_score','away_score','home_first_half_score','away_first_half_score'].forEach(k => {
    data[k] = data[k] === '' ? null : Number(data[k]);
  });
  if (data.home_first_half_score === null && data.away_first_half_score === null) {
    delete data.home_first_half_score; delete data.away_first_half_score;
  }
  status.textContent = 'Saving completed game…';
  try {
    const response = await fetch('/games', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || result.error || 'Could not save game');
    status.textContent = `Saved game #${result.id}: ${result.home} ${result.home_score}–${result.away_score} ${result.away}.`;
    gameForm.reset();
  } catch (error) { status.textContent = `Error: ${error.message}. Is the SmartBet API server running?`; }
});
const analysisForm = document.querySelector('#match-analysis-form');
if (analysisForm) analysisForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const output = document.querySelector('#match-analysis-result');
  const data = Object.fromEntries(new FormData(analysisForm).entries());
  const params = new URLSearchParams({sport:data.sport,home:data.home,away:data.away});
  let endpoint = '/predict/' + encodeURIComponent(data.sport);
  if (data.market === 'winner') { params.delete('sport'); endpoint += '?' + params.toString(); }
  else {
    if (data.line === '') { output.textContent = 'Enter a points/goals line for a totals analysis.'; return; }
    params.set('line',data.line);
    if (data.market === 'first_half_total') params.set('first_half','true');
    endpoint = '/analysis/total?' + params.toString();
  }
  output.textContent = 'Analysing entered match history…';
  try {
    const response = await fetch(endpoint); const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Analysis failed');
    if (result.status === 'insufficient_data') {
      output.innerHTML = `<strong>Not enough data yet</strong><p>${escapeHtml(result.message)}</p><p>Records available: ${result.sample_size}</p>`;
    } else if (result.market) {
      output.innerHTML = `<strong>${escapeHtml(result.market.replaceAll('_',' ').toUpperCase())}: ${escapeHtml(result.home)} vs ${escapeHtml(result.away)}</strong><div class="analysis-result-grid"><span>Over ${escapeHtml(String(result.line))}: <b>${Math.round(result.over_probability*100)}%</b></span><span>Under ${escapeHtml(String(result.line))}: <b>${Math.round(result.under_probability*100)}%</b></span><span>Historical average: <b>${result.historical_average}</b></span><span>Sample size: <b>${result.sample_size}</b></span></div><p class="analysis-warning">${escapeHtml(result.warning)}</p>`;
    } else {
      output.innerHTML = `<strong>Elo matchup estimate: ${escapeHtml(result.home)} vs ${escapeHtml(result.away)}</strong><div class="analysis-result-grid"><span>Home win: <b>${Math.round(result.home_win_prob*100)}%</b></span><span>Away win: <b>${Math.round(result.away_win_prob*100)}%</b></span><span>Historical records: <b>${result.rating_sample_size}</b></span></div><p class="analysis-warning">${escapeHtml(result.note)}</p>`;
    }
  } catch (error) { output.textContent = `Error: ${error.message}. Check that the API server is running.`; }
});


// Historical ML workflow: ESPN results -> leakage-controlled dataset -> trained model -> fixtures.
const mlSport = document.querySelector('#ml-sport');
const mlStatus = document.querySelector('#ml-status');
const mlUpcoming = document.querySelector('#ml-upcoming-list');
const mlKeyInput = document.querySelector('#ml-api-key');
if (mlKeyInput) { mlKeyInput.value = sessionStorage.getItem('smartbet-ml-key') || ''; mlKeyInput.addEventListener('input', () => sessionStorage.setItem('smartbet-ml-key', mlKeyInput.value)); }
async function mlRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const apiKey = mlKeyInput?.value.trim();
  if (apiKey) headers.set('X-API-Key', apiKey);
  const response = await fetch(path, {...options, headers});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.message || `Request failed (${response.status})`);
  return body;
}
const mlIngest = document.querySelector('#ml-ingest');
if (mlIngest) mlIngest.addEventListener('click', async () => {
  const sport = mlSport.value;
  const days = Math.max(1, Math.min(3650, Number(document.querySelector('#ml-days').value) || 730));
  mlStatus.textContent = `Importing ${sport.toUpperCase()} completed results from the public scoreboard…`;
  mlIngest.disabled = true;
  try { const r = await mlRequest(`/ml/ingest/${encodeURIComponent(sport)}?days_back=${days}`, {method:'POST'});
    mlStatus.innerHTML = `<strong>${escapeHtml(r.sport.toUpperCase())} import complete</strong><div class="analysis-result-grid"><span>Completed games found: <b>${r.completed_games_seen}</b></span><span>New historical records: <b>${r.new_games}</b></span></div><p>Source: ${escapeHtml(r.source)}. Next, train the model.</p>`;
  } catch(e) { mlStatus.textContent = `Import failed: ${e.message}`; } finally { mlIngest.disabled = false; }
});
const mlTrain = document.querySelector('#ml-train');
if (mlTrain) mlTrain.addEventListener('click', async () => {
  mlStatus.textContent = `Training and time-validating ${mlSport.value.toUpperCase()} model…`; mlTrain.disabled = true;
  try { const r = await mlRequest(`/ml/train/${encodeURIComponent(mlSport.value)}`, {method:'POST'});
    const scores = Object.entries(r.holdout_results).map(([name,v]) => `<span>${escapeHtml(name)} · accuracy <b>${Math.round((v.accuracy || 0)*100)}%</b>${v.log_loss !== undefined ? ` · log loss <b>${v.log_loss}</b>` : ''}</span>`).join('');
    mlStatus.innerHTML = `<strong>Model trained: ${escapeHtml(r.chosen_model)}</strong><div class="analysis-result-grid"><span>Training games: <b>${r.trained_on}</b></span><span>Validation games: <b>${r.holdout_games}</b></span>${scores}</div><p>Validation uses a chronological holdout; metrics are historical and do not guarantee future performance.</p>`;
  } catch(e) { mlStatus.textContent = `Training failed: ${e.message}`; } finally { mlTrain.disabled = false; }
});
const mlLoadUpcoming = document.querySelector('#ml-upcoming');
if (mlLoadUpcoming) mlLoadUpcoming.addEventListener('click', async () => {
  mlUpcoming.textContent = 'Loading upcoming fixtures and model estimates…'; mlLoadUpcoming.disabled = true;
  try { const rows = await mlRequest(`/ml/upcoming/${encodeURIComponent(mlSport.value)}?days_ahead=7`);
    if (!rows.length) { mlUpcoming.textContent = 'No upcoming fixtures were returned for this competition in the next 7 days.'; return; }
    mlUpcoming.innerHTML = `<div class="ml-fixtures">${rows.map(g => `<article><small>${escapeHtml(g.date)}</small><strong>${escapeHtml(g.home)} vs ${escapeHtml(g.away)}</strong><span>${g.home_win_prob === null ? escapeHtml(g.note) : `Home win estimate: <b>${Math.round(g.home_win_prob*100)}%</b> · Away/draw: <b>${Math.round((1-g.home_win_prob)*100)}%</b>`}</span></article>`).join('')}</div>`;
  } catch(e) { mlUpcoming.textContent = `Could not load predictions: ${e.message}`; } finally { mlLoadUpcoming.disabled = false; }
});
