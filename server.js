const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { URL } = require('node:url');

const ROOT = __dirname;
const PORT = Number(process.env.PORT || 3000);
const API_KEY = process.env.API_FOOTBALL_KEY;
const MIME = {'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.json':'application/json; charset=utf-8'};

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  if (url.pathname === '/api/football/leagues') {
    if (req.method !== 'GET') return sendJson(res, 405, {error:'Method not allowed'});
    if (!API_KEY) return sendJson(res, 503, {error:'API_FOOTBALL_KEY is not configured on the server.'});
    const id = url.searchParams.get('id') || '39';
    const season = url.searchParams.get('season') || '2026';
    if (!/^\d+$/.test(id) || !/^\d{4}$/.test(season)) return sendJson(res, 400, {error:'Invalid league ID or season.'});
    try {
      const upstream = await fetch(`https://v3.football.api-sports.io/leagues?id=${encodeURIComponent(id)}&season=${encodeURIComponent(season)}`, {
        headers: {'x-apisports-key': API_KEY}
      });
      const body = await upstream.json();
      return sendJson(res, upstream.status, body);
    } catch (err) {
      return sendJson(res, 502, {error:'Could not reach API-Sports.', detail:err.message});
    }
  }
  const requested = url.pathname === '/' ? '/index.html' : url.pathname;
  const file = path.resolve(ROOT, '.' + requested);
  if (!file.startsWith(ROOT + path.sep)) return sendJson(res, 403, {error:'Forbidden'});
  fs.readFile(file, (err, data) => {
    if (err) return sendJson(res, 404, {error:'Not found'});
    res.writeHead(200, {'content-type':MIME[path.extname(file)] || 'application/octet-stream'});
    res.end(data);
  });
});
function sendJson(res, status, data) {
  res.writeHead(status, {'content-type':'application/json; charset=utf-8','cache-control':'no-store'});
  res.end(JSON.stringify(data));
}
server.listen(PORT, () => console.log(`SmartBet AI running at http://localhost:${PORT}`));
