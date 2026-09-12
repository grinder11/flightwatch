/* Flights tab. Moved out of index.html unchanged apart from using
   loadJSON() from site.js. Reads docs/data.json, written by
   `analyze.py --json`. */

let DATA = null;

function legLine(label, depart, arrive, durMin, stops){
  if(!depart || !arrive)
    return `<div class="leg"><b>${label}</b>
      <span class="legmeta">time not recorded for this observation</span></div>`;
  const off = dayOffset(depart, arrive);
  const offTag = off > 0 ? `<sup>+${off}</sup>` : '';
  return `<div class="leg"><b>${label}</b>
    <span class="time">${fmtClock(depart)} &rarr; ${fmtClock(arrive)}${offTag}</span>
    <span class="legmeta">${fmtDuration(durMin)} &middot; ${stopsText(stops)}</span></div>`;
}

function renderLegs(r){
  const parts = [legLine('Outbound', r.outbound_depart, r.outbound_arrive,
                          r.outbound_duration_min, r.outbound_stops)];
  parts.push(r.full_read
    ? legLine('Return', r.return_depart, r.return_arrive,
               r.return_duration_min, r.return_stops)
    : `<div class="leg"><b>Return</b>
        <span class="legmeta">not confirmed &mdash; outbound-only read</span></div>`);
  $('legs').innerHTML = parts.join('');
}

const GROUPS = [
  {key:'trip', label:'The Trip',
   lede:'The pairing this whole tracker exists to watch.'},
  {key:'lever', label:'7-Day Variants',
   lede:'One extra PTO day, priced two ways. Levers to know the cost of, not candidates until you decide to take the 7th day.'},
  {key:'nonstop', label:'Nonstop Variants',
   lede:'Same date pairs, nonstop forced both ways &mdash; prices the connection-avoidance premium.'},
  {key:'baseline', label:'Baselines',
   lede:'Not open jaw &mdash; a plain round trip, kept only to price the open-jaw and nonstop premiums against. Never a candidate for this trip.'},
];

function classify(r){
  if(r.target) return 'trip';
  if(r.role === 'baseline') return 'baseline';
  if(r.nonstop) return 'nonstop';
  return 'lever';
}

function bucket(routes){
  const b = {trip:[], lever:[], nonstop:[], baseline:[]};
  routes.forEach(r => b[classify(r)].push(r));
  return b;
}

function line(pts, w, h, pad){
  const ys = pts.map(p=>p.p);
  const lo = Math.min(...ys), hi = Math.max(...ys), span = (hi-lo)||1;
  const X = i => pad + (i/(Math.max(pts.length-1,1))) * (w-pad*2);
  const Y = v => pad + (1-(v-lo)/span) * (h-pad*2);
  return {d: pts.map((p,i)=>(i?'L':'M')+X(i).toFixed(1)+' '+Y(p.p).toFixed(1)).join(' '),
          Y, X, lo, hi};
}

function drawChart(route, floor){
  const svg = $('chart'), W=820, H=190, PAD=22;
  if(!route || !route.series || route.series.length < 2){
    // Collapse the frame rather than reserve 190px of empty plot area.
    svg.setAttribute('viewBox', `0 0 ${W} 26`);
    svg.innerHTML = `<text class="axis" x="0" y="16">Chart appears once this pairing has two days of history.</text>`;
    return;
  }
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const pts = route.series.slice(-120);
  const g = line(pts, W, H, PAD);
  const parts = [];
  if(floor && floor >= g.lo && floor <= g.hi)
    parts.push(`<line class="floorline" x1="0" x2="${W}" y1="${g.Y(floor)}" y2="${g.Y(floor)}"/>`,
               `<text class="axis" x="0" y="${g.Y(floor)-6}">floor ${usd(floor)}</text>`);
  parts.push(`<line class="p20line" x1="0" x2="${W}" y1="${g.Y(route.p20)}" y2="${g.Y(route.p20)}"/>`);
  parts.push(`<text class="axis" x="${W}" y="${g.Y(route.p20)-6}" text-anchor="end">good price ${usd(route.p20)}</text>`);
  parts.push(`<path class="trace" d="${g.d}"/>`);
  parts.push(`<circle cx="${g.X(pts.length-1)}" cy="${g.Y(pts[pts.length-1].p)}" r="3.6" fill="var(--trace)"/>`);
  parts.push(`<text class="axis" x="0" y="${H-2}">${pts[0].d}</text>`);
  parts.push(`<text class="axis" x="${W}" y="${H-2}" text-anchor="end">${pts[pts.length-1].d}</text>`);
  svg.innerHTML = parts.join('');
}

function verdictLine(r, floor){
  if(!r) return ['Waiting for the first poll.', ''];
  const p = usd(r.now);
  if(r.n < 5)
    return [`<span class="n">${p}</span> today, on ${r.n} day${r.n===1?'':'s'} of history.`,
            'Too thin to judge. The statistical rules stay disarmed until twelve observations exist.'];
  if(r.now <= floor)
    return [`<span class="n buy">${p}</span> &mdash; under your floor. Book it today.`,
            'This is the one alert that ignores history entirely.'];
  if(r.now <= r.min)
    return [`<span class="n buy">${p}</span> is the lowest this trip has ever been.`,
            `Previous low was ${usd(r.min)} across ${r.n} observations.`];
  if(r.now <= r.p20)
    return [`<span class="n buy">${p}</span> sits in the bottom fifth of everything seen.`,
            `A good price here is ${usd(r.p20)}; typical is ${usd(r.median)}. Strong, if the dates still hold.`];
  if(r.now <= r.median)
    return [`<span class="n">${p}</span>, below the typical price but not near the floor.`,
            `Typical ${usd(r.median)}, good price ${usd(r.p20)}, best ever ${usd(r.min)}. Defensible, not urgent.`];
  return [`<span class="n hold">${p}</span> today. That is above the typical price. Wait.`,
          `Typical ${usd(r.median)}, good price ${usd(r.p20)}, best ever seen ${usd(r.min)}.`];
}

function select(id){
  const r = (DATA.routes||[]).find(x=>x.id===id);
  if(!r) return;
  drawChart(r, DATA.floor);
  renderLegs(r);
  document.querySelectorAll('.rchip').forEach(c=>
    c.setAttribute('aria-pressed', String(c.dataset.id===id)));
  document.querySelectorAll('.route-row').forEach(t=>
    t.classList.toggle('sel', t.dataset.id===id));
  const span = r.n>1 ? `${r.series.length} days of history` : 'one observation';
  $('chartcap').innerHTML =
    `<b>${r.path||r.id}</b>, ${r.depart} to ${r.back} &middot; ${r.pto ?? '—'} PTO days &middot; `
    + `${span}. Now ${usd(r.now)}, best ever ${usd(r.min)}, good price ${usd(r.p20)}, typical ${usd(r.median)}. `
    + `Dashed line is the ${usd(DATA.floor)} book-on-sight floor.`;
}

function renderGroupRows(routes, cheapestId){
  return routes.map(r => {
    const over = r.pto > 6;
    // "Now" is coloured when it's at or under the good-price mark -- the
    // judgement the dropped verdict column used to spell out. Needs 5
    // observations first: with n=1 a price trivially equals its own p20,
    // which would paint every row green. Same threshold analyze.py uses
    // before it will give a verdict at all.
    const strong = r.n >= 5 && r.now <= r.p20;
    const badge = r.id === cheapestId ? '<span class="badge">cheapest now</span>' : '';
    return `<tr class="route-row" data-id="${r.id}">
      <td><span class="rid">${r.path || r.id}</span>${badge}
          <span class="meta">${r.depart} &rarr; ${r.back}${r.target?' &middot; the trip':''}</span></td>
      <td class="${over?'over':''}">${r.pto ?? '—'}${over?'&#8202;+':''}</td>
      <td class="${strong?'v good':''}">${usd(r.now)}</td>
      <td>${usd(r.p20)}</td><td>${usd(r.median)}</td>
    </tr>`;
  }).join('');
}

function renderStats(routes, target){
  if(!target) return;
  const obs = routes.reduce((a,r)=>a+r.n,0);
  const nonBaseline = routes.filter(r => r.role !== 'baseline');
  const cheapest = nonBaseline.length
    ? nonBaseline.reduce((a,b) => b.now < a.now ? b : a) : null;
  const under = target.n >= 5 && target.now <= target.p20;
  // Each tile is one figure. A second value goes on its own sub-line rather
  // than beside it, where it wraps mid-number at narrow widths.
  $('stats').innerHTML = [
    ['The trip, today', usd(target.now), under ? 'buy' : '', ''],
    ['Best ever seen', usd(target.min), '', ''],
    ['Good price', usd(target.p20), '', `typical ${usd(target.median)}`],
    ['Cheapest option', cheapest ? usd(cheapest.now) : '—', '',
      cheapest && cheapest.id !== target.id ? 'not the trip' : ''],
    ['Observations', String(obs), '', `${routes.length} pairings`],
  ].map(([k,v,cls,sub]) =>
    `<div class="stat"><span class="k">${k}</span>
      <span class="v ${cls}">${v}</span>
      ${sub ? `<span class="k" style="margin:4px 0 0">${sub}</span>` : ''}</div>`
  ).join('');
}

function render(data){
  DATA = data;
  const routes = data.routes || [];
  const target = routes.find(r => r.target) || routes[0];
  const [v, s] = verdictLine(target, data.floor);
  $('verdict').innerHTML = v;
  if(s) $('sub').innerHTML = s;

  if(data.sample)
    $('flag').innerHTML = '<span class="flag">Sample data. Nothing has been polled yet.</span>';

  if(!routes.length){
    $('stats').hidden = true;   // an empty grid still draws its border box
    drawChart(null, data.floor);
    return;
  }

  const buckets = bucket(routes);
  const orderedRoutes = GROUPS.flatMap(g => buckets[g.key]);
  const nonBaseline = routes.filter(r => r.role !== 'baseline');
  const cheapest = nonBaseline.length
    ? nonBaseline.reduce((a,b) => b.now < a.now ? b : a)
    : null;

  renderStats(routes, target);

  $('rchips').innerHTML = orderedRoutes.map(r=>
    `<button class="rchip${r.role==='baseline'?' baseline':''}" data-id="${r.id}" aria-pressed="false">${
      r.target?'The trip':(r.path||r.id)}<span class="p">${usd(r.now)}</span></button>`).join('');

  $('groups').innerHTML = GROUPS.filter(g => buckets[g.key].length).map(g => `
    <div class="group">
      <h3 class="grouphead">${g.label} <span class="count">${buckets[g.key].length}</span></h3>
      <p class="glede">${g.lede}</p>
      <div class="scroll"><table>
        <thead><tr>
          <th>Pairing</th><th>PTO</th><th>Now</th>
          <th>Good price</th><th>Typical</th>
        </tr></thead>
        <tbody>${renderGroupRows(buckets[g.key], cheapest && cheapest.id)}</tbody>
      </table></div>
    </div>`).join('');

  select(target.id);

  const obs = routes.reduce((a,r)=>a+r.n,0);
  $('stamp').textContent =
    `${obs} observations across ${routes.length} pairings. Last poll ` +
    (data.generated ? new Date(data.generated).toLocaleString('en-US',
      {dateStyle:'medium', timeStyle:'short'}) : 'unknown') + '.';
}

$('rchips').addEventListener('click', e=>{
  const c = e.target.closest('.rchip'); if(c) select(c.dataset.id);
});
$('groups').addEventListener('click', e=>{
  const t = e.target.closest('.route-row'); if(t && t.dataset.id) select(t.dataset.id);
});

const SAMPLE = {sample:true, floor:900, generated:null, routes:[]};
loadJSON('data.json').then(d => {
  if(d && d.routes && d.routes.length) return render(d);
  render(SAMPLE);
  if(!d) $('flag').innerHTML = `<span class="flag">No data loaded. ${SERVE_HINT}</span>`;
});
