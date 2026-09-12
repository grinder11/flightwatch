/* Landing page. Pulls the headline number off data.json and the plan state
   off itinerary.json, then renders the milestone countdown. Everything here
   degrades to a dash if a payload is missing -- no tab should look broken
   before its data exists. */

const DEPARTURE = '2027-05-14';

function daysUntil(iso){
  const then = new Date(iso + 'T00:00:00Z'), now = new Date();
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Math.round((then - today) / 86400000);
}

function renderStats(target, it){
  const out = daysUntil(DEPARTURE);
  const tiles = [
    ['Days to departure', out > 0 ? out : 'now', '',
      out > 0 ? '14 May 2027' : ''],
    ['The trip, today', target ? usd(target.now) : '—',
      target && target.n >= 5 && target.now <= target.p20 ? 'buy' : '',
      target ? (target.n >= 5 ? `20th %ile ${usd(target.p20)}`
                              : `${target.n} day${target.n === 1 ? '' : 's'} of history`)
             : 'no fares polled yet'],
    ['Nights on the ground', it ? it.nights_total : '—', '',
      it ? it.cities.map(c => `${esc(c.name)} ${c.nights}`).join(' · ') : ''],
    ['Booked', it ? `${it.counts.booked || 0} <span class="u">/ ${it.bookings.length}</span>` : '—',
      '', it ? 'flights, hotels, rail' : ''],
  ];
  $('stats').innerHTML = tiles.map(([k, v, cls, sub]) =>
    `<div class="stat"><span class="k">${k}</span>
      <span class="v ${cls}">${v}</span>
      ${sub ? `<span class="k" style="margin:4px 0 0">${sub}</span>` : ''}</div>`
  ).join('');
}

function renderCards(target, it){
  const cards = [
    ['flights.html', 'Flights',
      target ? `${usd(target.now)} today` : 'awaiting first poll',
      'Every date pairing priced against its own history, with the chart and '
      + 'the stop-by-stop read on each leg.'],
    ['itinerary.html', 'Itinerary',
      it ? `${it.days.length} days mapped` : 'not built yet',
      'Day by day from Haneda to Kansai, plus every booking that still needs '
      + 'paying for.'],
    ['plans.html', 'Plans',
      'empty for now',
      'Concrete detail plans — sumo, rail, eSIMs, luggage. Filled in when '
      + 'they are real.'],
  ];
  $('cards').innerHTML = cards.map(([href, title, meta, body]) =>
    `<a class="card cardlink" href="${href}">
      <div class="cardhead"><h3>${title}</h3><span class="aside">${meta}</span></div>
      <p class="lede" style="margin:0">${body}</p>
    </a>`).join('');
}

function renderMilestones(milestones){
  if(!milestones || !milestones.length){ $('sec-milestones').hidden = true; return; }
  const nextIdx = milestones.findIndex(m => daysUntil(m.date) >= 0);
  $('milestones').innerHTML = milestones.map((m, i) => {
    const left = daysUntil(m.date);
    const done = left < 0;
    const {dow, day} = fmtDay(m.date);
    const year = m.date.slice(0, 4);
    const pill = done
      ? '<span class="pill booked">Done</span>'
      : i === nextIdx
        ? `<span class="pill watch">Next &middot; ${left} day${left === 1 ? '' : 's'}</span>`
        : `<span class="pill">${left} days</span>`;
    return `<li class="day${done ? ' transit' : ''}">
      <div class="dstamp"><b>${day}</b>${year} &middot; ${dow}</div>
      <div class="dbody">
        <h4>${esc(m.name)} ${pill}</h4>
        ${m.note ? `<p>${esc(m.note)}</p>` : ''}
      </div>
    </li>`;
  }).join('');
}

Promise.all([loadJSON('data.json'), loadJSON('itinerary.json')])
  .then(([data, it]) => {
    const routes = (data && data.routes) || [];
    const target = routes.find(r => r.target) || routes[0] || null;
    const itin = it && it.days ? it : null;

    renderStats(target, itin);
    renderCards(target, itin);
    renderMilestones(itin && itin.milestones);

    const bits = [];
    if(data && data.generated)
      bits.push('Fares last polled ' + new Date(data.generated)
        .toLocaleString('en-US', {dateStyle:'medium', timeStyle:'short'}));
    if(routes.length)
      bits.push(`${routes.reduce((a,r)=>a+r.n,0)} observations across ${routes.length} pairings`);
    $('stamp').textContent = bits.join(' · ') + (bits.length ? '.' : '');
  });
