/* Itinerary tab. Reads docs/itinerary.json (built from itinerary.yaml by
   `analyze.py --json`) and borrows the target fare from data.json so one
   page answers "is the trip affordable and planned." */

const STATUS = {
  booked:   {cls:'booked', label:'Booked'},
  watching: {cls:'watch',  label:'Watching'},
  open:     {cls:'',       label:'Not booked'},
};

function renderStats(it, fare){
  const cities = it.cities.map(c => `${esc(c.name)} ${c.nights}`).join(' · ');
  const total = it.bookings.length;
  const booked = it.counts.booked || 0;
  const tiles = [
    ['Nights on the ground', it.nights_total, ''],
    ['Cities', it.cities.length, cities],
    ['Booked', `${booked} <span class="u">/ ${total}</span>`, ''],
  ];
  if(fare) tiles.push(['The trip, today', usd(fare.now), '']);
  $('stats').innerHTML = tiles.map(([k, v, u]) =>
    `<div class="stat"><span class="k">${k}</span>
      <span class="v">${v}</span>
      ${u ? `<span class="k" style="margin-top:4px">${u}</span>` : ''}</div>`
  ).join('');
}

function renderDays(days){
  $('days').innerHTML = days.map(d => {
    const {dow, day} = fmtDay(d.date);
    const city = d.transit ? 'In transit' : d.city;
    return `<li class="day${d.transit ? ' transit' : ''}">
      <div class="dstamp"><b>${day}</b>${dow}</div>
      <div class="dbody">
        <h4>${esc(d.title)}</h4>
        <span class="dcity">${esc(city)}</span>
        ${d.note ? `<p>${esc(d.note)}</p>` : ''}
      </div>
    </li>`;
  }).join('');
}

function renderBookings(bookings){
  const rows = bookings.map(b => {
    const s = STATUS[b.status] || STATUS.open;
    return `<tr>
      <td><span class="rid">${esc(b.what)}</span>
        ${b.note ? `<span class="meta">${esc(b.note)}</span>` : ''}</td>
      <td>${esc(b.when) || '—'}</td>
      <td>${b.cost_usd == null ? '—' : usd(b.cost_usd)}</td>
      <td><span class="pill ${s.cls}">${s.label}</span></td>
    </tr>`;
  }).join('');
  $('bookings').innerHTML = `<div class="scroll"><table>
    <thead><tr><th>What</th><th>When</th><th>Cost</th><th>Status</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function render(it, fare){
  const t = it.trip || {};
  const span = it.days.length
    ? `${fmtDay(it.days[0].date).day} – ${fmtDay(it.days[it.days.length-1].date).day} 2027`
    : '';
  $('verdict').innerHTML = `${esc(t.title || 'The trip')}, `
    + `<span class="n">${it.nights_total}</span> nights on the ground.`;
  $('sub').innerHTML = [
    span,
    it.cities.map(c => `${esc(c.name)} ${c.nights}`).join(' · '),
    t.party ? `${t.party} travelling` : '',
  ].filter(Boolean).join(' &middot; ') + (t.note ? `. ${esc(t.note)}` : '');

  renderStats(it, fare);
  renderDays(it.days);
  renderBookings(it.bookings);

  $('stamp').textContent = it.generated
    ? 'Built from itinerary.yaml on ' + new Date(it.generated)
        .toLocaleString('en-US', {dateStyle:'medium', timeStyle:'short'}) + '.'
    : '';
}

function renderEmpty(){
  // A missing file and a blocked fetch look identical from here, so the
  // message covers both rather than guessing which one happened.
  $('verdict').textContent = 'No itinerary yet.';
  $('sub').innerHTML = 'Nothing at <code>itinerary.json</code>. Build it with '
    + '<code>python analyze.py --json</code> &mdash; or, if you opened this page '
    + 'straight from disk, serve it instead: '
    + '<code>cd docs &amp;&amp; python3 -m http.server 8000</code>.';
  $('stats').hidden = true;   // an empty grid still draws its border box
  $('sec-days').hidden = true;
  $('sec-bookings').hidden = true;
  $('shell').innerHTML = `<div class="empty">
    <h3>Nothing planned on this page yet</h3>
    <p>The day-by-day plan and the booking list are both generated from
    <code>itinerary.yaml</code>. Days come from its <code>days:</code> list and
    nights-per-city are counted from them, so there is no second place to keep
    in sync.</p></div>`;
}

Promise.all([loadJSON('itinerary.json'), loadJSON('data.json')])
  .then(([it, data]) => {
    if(!it || !it.days){ renderEmpty(); return; }
    const routes = (data && data.routes) || [];
    render(it, routes.find(r => r.target) || routes[0] || null);
  });
