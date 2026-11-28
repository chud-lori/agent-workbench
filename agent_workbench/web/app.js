'use strict';

(function () {
  // Note text is untrusted (pasted logs, code): it only ever reaches the page through textContent.
  const KINDS = ['gotcha', 'fact', 'reference', 'preference', 'note', 'decision', 'todo'];
  const SLOTS = 7;
  const LABEL_ZOOM = 4;
  const LIST_LIMIT = 50;
  const LABELLED_MATCHES = 12;
  const MIN_HIT_PX = 8;
  const LABELLED_HUBS = 10;
  const MAX_FIT_ZOOM = 8;

  const $ = (id) => document.getElementById(id);
  const token = new URLSearchParams(location.search).get('token') || '';
  const embedded = $('graph-data');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const darkScheme = matchMedia('(prefers-color-scheme: dark)');

  let data = { nodes: [], edges: [], dangling: [] };
  let byId = new Map();
  let projectSlot = new Map();
  let theme = {};
  let fg = null;
  let visible = { nodes: [], links: [] };
  let selectedId = null;
  let focus = null;
  let matches = null;
  let lit = null;
  let topMatches = new Set();
  let hubs = new Set();
  let hoverId = null;
  let searchRun = 0;

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function count(n, word) {
    return n.toLocaleString() + ' ' + word + (n === 1 ? '' : 's');
  }

  function ref(node) {
    return node.kind + '#' + node.id;
  }

  function api(path) {
    return fetch(path + (path.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(token)).then((response) => {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    });
  }

  function readTheme() {
    const style = getComputedStyle(document.documentElement);
    const get = (name) => style.getPropertyValue(name).trim();
    theme = {
      surface: get('--surface'),
      ink: get('--ink'),
      edge: get('--edge'),
      edgeStrong: get('--edge-strong'),
      edgeFaint: get('--edge-faint'),
      other: get('--other'),
      font: getComputedStyle(document.body).fontFamily,
      slots: Array.from({ length: SLOTS }, (_, i) => get('--slot-' + (i + 1))),
    };
  }

  function colourOf(node) {
    if ($('colour').value === 'project') {
      const slot = projectSlot.get(node.project);
      return slot === undefined ? theme.other : theme.slots[slot];
    }
    return theme.slots[KINDS.indexOf(node.kind)] || theme.other;
  }

  function swatch(colour) {
    const mark = el('span', undefined, 'swatch');
    mark.style.background = colour;
    return mark;
  }

  function dayBound(value, end) {
    return value ? new Date(value + (end ? 'T23:59:59' : 'T00:00:00')).getTime() / 1000 : null;
  }

  function filters() {
    return {
      kinds: new Set(KINDS.filter((kind) => $('kind-' + kind).checked)),
      project: $('project').value,
      tag: $('tag').value.trim().toLowerCase(),
      since: dayBound($('since').value, false),
      until: dayBound($('until').value, true),
      resolved: $('resolved').checked,
      superseded: $('superseded').checked,
      unlinked: $('unlinked').checked,
    };
  }

  function passes(node, f) {
    if (!f.kinds.has(node.kind)) return false;
    if (f.project && node.project !== f.project) return false;
    if (f.tag && !node.tags.some((tag) => tag.toLowerCase() === f.tag)) return false;
    if (f.since !== null && node.created_at < f.since) return false;
    if (f.until !== null && node.created_at > f.until) return false;
    if (node.resolved && !f.resolved) return false;
    if (node.superseded_by && !f.superseded) return false;
    return true;
  }

  function withinHops(ids, edges, start, hops) {
    const keep = new Set([start]);
    let frontier = new Set([start]);
    for (let step = 0; step < hops && frontier.size; step++) {
      const next = new Set();
      for (const edge of edges) {
        for (const [from, to] of [[edge.source, edge.target], [edge.target, edge.source]]) {
          if (frontier.has(from) && ids.has(to) && !keep.has(to)) {
            keep.add(to);
            next.add(to);
          }
        }
      }
      frontier = next;
    }
    return keep;
  }

  function computeVisible() {
    const f = filters();
    let ids = new Set(data.nodes.filter((node) => passes(node, f)).map((node) => node.id));
    if (focus && ids.has(focus.id)) ids = withinHops(ids, data.edges, focus.id, focus.hops);
    const edges = data.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
    const linked = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
    const orphans = data.nodes.filter((node) => ids.has(node.id) && !linked.has(node.id));
    // Unlinked notes carry no structure and ring the overview, so they are listed rather than drawn by default.
    if (!f.unlinked) for (const node of orphans) if (!focus || node.id !== focus.id) ids.delete(node.id);
    return {
      orphans,
      nodes: data.nodes.filter((node) => ids.has(node.id)),
      // force-graph replaces source/target with node objects, so it gets copies.
      links: edges.map((edge) => ({ source: edge.source, target: edge.target, type: edge.type })),
      edges,
    };
  }

  function render() {
    visible = computeVisible();
    fg.graphData({ nodes: visible.nodes, links: visible.links });
    hubs = new Set([...visible.nodes].filter((node) => node.cited_by > 0)
      .sort((a, b) => b.cited_by - a.cited_by).slice(0, LABELLED_HUBS).map((node) => node.id));
    const total = data.nodes.length.toLocaleString();
    let summary = visible.nodes.length.toLocaleString() + ' of ' + total + ' notes, ' + count(visible.links.length, 'link');
    if (focus) summary += '. Focused on ' + ref(byId.get(focus.id)) + ', ' + count(focus.hops, 'hop');
    $('summary').textContent = summary;
    if (!data.nodes.length) {
      showStageMessage('This brain has no notes yet. Store one with brain_remember or run_cli.py remember, then reload.');
    } else if (!visible.nodes.length) {
      showStageMessage('No notes match these filters.', true);
    } else {
      $('stage-message').hidden = true;
    }
    renderHealth();
    renderResults();
    redraw();
  }

  function showStageMessage(text, offerClear) {
    const box = $('stage-message');
    box.replaceChildren(el('p', text));
    if (offerClear) {
      const button = el('button', 'Clear filters');
      button.type = 'button';
      button.addEventListener('click', clearFilters);
      box.append(button);
    }
    box.hidden = false;
  }

  function noteButton(node) {
    const button = el('button', ref(node), 'ref');
    button.type = 'button';
    button.addEventListener('click', () => select(node.id, true));
    return button;
  }

  function noteItem(node, suffix) {
    const item = el('li');
    item.append(noteButton(node), ' ', el('span', suffix || node.title, 'title'));
    return item;
  }

  function fillList(list, titleEl, title, items, emptyText) {
    titleEl.textContent = title + ' (' + items.length.toLocaleString() + ')';
    list.replaceChildren(...items.slice(0, LIST_LIMIT));
    if (!items.length) list.append(el('li', emptyText, 'empty'));
    if (items.length > LIST_LIMIT) list.append(el('li', 'and ' + (items.length - LIST_LIMIT).toLocaleString() + ' more', 'empty'));
  }

  function renderHealth() {
    const inDegree = new Map();
    for (const edge of visible.edges) {
      if (edge.type === 'cites') inDegree.set(edge.target, (inDegree.get(edge.target) || 0) + 1);
    }
    const cited = [...inDegree].sort((a, b) => b[1] - a[1] || a[0] - b[0]).slice(0, 10)
      .map(([id, times]) => noteItem(byId.get(id), 'cited ' + count(times, 'time')));
    fillList($('cited-list'), $('cited-title'), 'Most cited', cited, 'No note in view is cited by another.');
    const orphans = visible.orphans.map((node) => noteItem(node));
    fillList($('orphans-list'), $('orphans-title'), 'Orphans', orphans, 'Every note in view links to another.');
    const shownIds = new Set(visible.nodes.map((node) => node.id));
    const dangling = data.dangling.filter((entry) => shownIds.has(entry.from))
      .map((entry) => noteItem(byId.get(entry.from), 'cites #' + entry.to + ', which does not exist'));
    fillList($('dangling-list'), $('dangling-title'), 'Missing references', dangling, 'Every reference points to a real note.');
  }

  function renderResults() {
    const section = $('results');
    if (!matches) {
      section.hidden = true;
      return;
    }
    const shown = new Set(visible.nodes.map((node) => node.id));
    const hits = [...matches].map((id) => byId.get(id));
    const hidden = hits.filter((node) => !shown.has(node.id)).length;
    let title = hits.length ? (hits.length === 1 ? '1 match' : hits.length.toLocaleString() + ' matches') : 'No notes match this search';
    if (hidden) title += ', ' + hidden.toLocaleString() + ' hidden by filters';
    $('results-title').textContent = title;
    const list = $('results-list');
    list.replaceChildren(...hits.slice(0, LIST_LIMIT).map((node) => noteItem(node)));
    if (hits.length > LIST_LIMIT) list.append(el('li', 'and ' + (hits.length - LIST_LIMIT).toLocaleString() + ' more', 'empty'));
    section.hidden = false;
  }

  function redraw() {
    lit = null;
    topMatches = new Set();
    if (matches) {
      lit = matches;
      // Matches arrive best first; only the strongest few are labelled, or a broad query buries the view in text.
      const shown = new Set(visible.nodes.map((node) => node.id));
      topMatches = new Set([...matches].filter((id) => shown.has(id)).slice(0, LABELLED_MATCHES));
    } else if (egoId() !== null) {
      lit = neighbourhood(egoId());
    }
    // Re-setting an accessor makes force-graph repaint without reheating the simulation.
    fg.nodeColor(nodeColour).linkColor(linkColour);
  }

  function egoId() {
    return selectedId !== null ? selectedId : hoverId;
  }

  function neighbourhood(id) {
    const ids = new Set([id]);
    for (const edge of visible.edges) {
      if (edge.source === id) ids.add(edge.target);
      if (edge.target === id) ids.add(edge.source);
    }
    return ids;
  }

  function nodeColour(node) {
    const colour = colourOf(node);
    return lit && !lit.has(node.id) ? colour + '33' : colour;
  }

  function linkColour(link) {
    if (!lit) return link.type === 'supersedes' ? theme.edgeStrong : theme.edge;
    const source = typeof link.source === 'object' ? link.source.id : link.source;
    const target = typeof link.target === 'object' ? link.target.id : link.target;
    const touches = matches ? lit.has(source) && lit.has(target) : source === egoId() || target === egoId();
    return touches ? theme.edgeStrong : theme.edgeFaint;
  }

  function drawExtras(node, ctx, scale) {
    const radius = Math.sqrt(1 + node.cited_by) * 3;
    if (node.id === selectedId) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius + 2 / scale, 0, 2 * Math.PI);
      ctx.strokeStyle = theme.ink;
      ctx.lineWidth = 2 / scale;
      ctx.stroke();
    }
  }

  function wantsLabel(node, scale) {
    // Overview labels only the most cited notes; a selection or hover labels its neighbourhood instead.
    if (!lit) return scale >= LABEL_ZOOM || hubs.has(node.id);
    if (!lit.has(node.id)) return false;
    return matches ? topMatches.has(node.id) || scale >= LABEL_ZOOM : true;
  }

  function labelRank(node) {
    if (node.id === egoId()) return -1;
    return -node.cited_by;
  }

  // Labels are drawn after the nodes, most important first, and a label that would overlap one already drawn is skipped.
  function drawLabels(ctx, scale) {
    const nodes = visible.nodes.filter((node) => node.x !== undefined && wantsLabel(node, scale))
      .sort((a, b) => labelRank(a) - labelRank(b));
    const placed = [];
    const height = 13 / scale;
    ctx.font = 11 / scale + 'px ' + theme.font;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.lineJoin = 'round';
    ctx.lineWidth = 3 / scale;
    ctx.strokeStyle = theme.surface;
    ctx.fillStyle = theme.ink;
    for (const node of nodes) {
      const title = node.title.length > 40 ? node.title.slice(0, 39) + '…' : node.title;
      const width = ctx.measureText(title).width;
      const top = node.y + Math.sqrt(1 + node.cited_by) * 3 + 2 / scale;
      const box = { left: node.x - width / 2, right: node.x + width / 2, top, bottom: top + height };
      if (placed.some((p) => box.left < p.right && box.right > p.left && box.top < p.bottom && box.bottom > p.top)) continue;
      placed.push(box);
      ctx.strokeText(title, node.x, top);
      ctx.fillText(title, node.x, top);
    }
  }

  function zoomToNeighbourhood(id) {
    const nodes = [...neighbourhood(id)].map((nid) => byId.get(nid)).filter((n) => n.x !== undefined);
    const xs = nodes.map((n) => n.x);
    const ys = nodes.map((n) => n.y);
    const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const stage = $('graph').parentElement;
    const pad = 80;
    const fit = Math.min((stage.clientWidth - 2 * pad) / (maxX - minX || 1), (stage.clientHeight - 2 * pad) / (maxY - minY || 1));
    fg.centerAt((minX + maxX) / 2, (minY + maxY) / 2, motionMs(500));
    fg.zoom(Math.min(fit, MAX_FIT_ZOOM), motionMs(500));
  }

  function paintHitArea(node, colour, ctx, scale) {
    const radius = Math.max(Math.sqrt(1 + node.cited_by) * 3, MIN_HIT_PX / scale);
    ctx.fillStyle = colour;
    ctx.beginPath();
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI);
    ctx.fill();
  }

  function showHover(node) {
    const card = $('hover');
    hoverId = node ? node.id : null;
    if (selectedId === null && !matches) redraw();
    $('graph').style.cursor = node ? 'pointer' : '';
    if (!node) {
      card.hidden = true;
      return;
    }
    const links = node.cited_by ? ' · cited ' + count(node.cited_by, 'time') : '';
    card.replaceChildren(el('code', ref(node)), el('span', node.title), el('small', (node.project || 'no project') + links));
    card.hidden = false;
  }

  function motionMs(ms) {
    return reducedMotion.matches ? 0 : ms;
  }

  function select(id, centre) {
    selectedId = id;
    const node = byId.get(id);
    $('note').hidden = false;
    const title = $('note-title');
    title.replaceChildren(swatch(colourOf(node)), el('code', ref(node)), el('span', node.kind));
    $('focus').textContent = focus && focus.id === id ? 'Show whole graph' : 'Focus on this note';
    const meta = $('note-meta');
    const shown = visible.nodes.includes(node);
    const rows = [
      ['Project', node.project || 'none'],
      ['Tags', node.tags.join(' ') || 'none'],
      ['Stored', new Date(node.created_at * 1000).toLocaleDateString('en-CA')],
      ['Status', [node.resolved ? 'resolved' : 'open', node.superseded_by ? 'superseded by #' + node.superseded_by : '',
        shown ? '' : 'hidden by filters'].filter(Boolean).join(', ')],
    ];
    meta.replaceChildren(...rows.flatMap(([term, value]) => [el('dt', term), el('dd', value)]));
    renderLinks(node);
    const body = $('note-body');
    if (node.content !== undefined) {
      body.textContent = node.content;
    } else {
      body.textContent = 'Loading the note…';
      api('note/' + id).then((full) => {
        if (selectedId === id) body.textContent = full.content;
      }).catch((error) => {
        if (selectedId === id) body.textContent = 'Could not load this note (' + error.message + '). Is the server still running?';
      });
    }
    if (centre) title.focus();
    redraw();
    if (shown && node.x !== undefined) zoomToNeighbourhood(id);
  }

  function renderLinks(node) {
    const groups = [
      ['Cites', (edge) => edge.type === 'cites' && edge.source === node.id, 'target'],
      ['Cited by', (edge) => edge.type === 'cites' && edge.target === node.id, 'source'],
      ['Replaces', (edge) => edge.type === 'supersedes' && edge.source === node.id, 'target'],
      ['Replaced by', (edge) => edge.type === 'supersedes' && edge.target === node.id, 'source'],
    ];
    const box = $('note-links');
    box.replaceChildren();
    for (const [label, test, end] of groups) {
      const linked = data.edges.filter(test).map((edge) => byId.get(edge[end]));
      if (!linked.length && label.startsWith('Replace')) continue;
      box.append(el('h3', label + ' (' + linked.length + ')'));
      const list = el('ul');
      list.append(...linked.map((other) => noteItem(other)));
      if (!linked.length) list.append(el('li', 'None.', 'empty'));
      box.append(list);
    }
  }

  function closeNote() {
    selectedId = null;
    $('note').hidden = true;
    redraw();
  }

  function toggleFocus() {
    focus = focus && focus.id === selectedId ? null : { id: selectedId, hops: Number($('hops').value) };
    render();
    select(selectedId, false);
    fg.zoomToFit(motionMs(400), 40);
  }

  function clearFilters() {
    for (const kind of KINDS) $('kind-' + kind).checked = true;
    for (const id of ['project', 'tag', 'since', 'until']) $(id).value = '';
    $('resolved').checked = false;
    $('superseded').checked = false;
    $('unlinked').checked = false;
    focus = null;
    render();
  }

  function search(query) {
    const run = ++searchRun;
    if (!query.trim()) {
      matches = null;
      render();
      return;
    }
    const found = embedded ? Promise.resolve(localSearch(query)) : api('search.json?q=' + encodeURIComponent(query)).then((r) => r.ids);
    found.then((ids) => {
      if (run !== searchRun) return;
      matches = new Set(ids.filter((id) => byId.has(id)));
      render();
      if (topMatches.size) {
        fg.zoomToFit(motionMs(400), 60, (node) => topMatches.has(node.id));
      }
    }).catch((error) => {
      $('results').hidden = false;
      $('results-title').textContent = 'Search failed (' + error.message + ')';
      $('results-list').replaceChildren();
    });
  }

  function localSearch(query) {
    const terms = query.toLowerCase().split(/\s+/).filter((term) => term.length > 1);
    const scored = data.nodes.map((node) => {
      const text = (node.title + ' ' + (node.content || '')).toLowerCase();
      return [node.id, terms.filter((term) => text.includes(term)).length];
    });
    return scored.filter(([, score]) => score).sort((a, b) => b[1] - a[1]).map(([id]) => id);
  }

  function buildControls() {
    const kindCounts = new Map();
    const projectCounts = new Map();
    const tags = new Set();
    for (const node of data.nodes) {
      kindCounts.set(node.kind, (kindCounts.get(node.kind) || 0) + 1);
      projectCounts.set(node.project, (projectCounts.get(node.project) || 0) + 1);
      node.tags.forEach((tag) => tags.add(tag));
    }
    $('kinds').replaceChildren(...KINDS.map((kind) => {
      const label = el('label');
      const box = el('input');
      box.type = 'checkbox';
      box.id = 'kind-' + kind;
      box.checked = true;
      box.addEventListener('change', render);
      label.append(box, swatch(theme.slots[KINDS.indexOf(kind)]), kind + ' ' + (kindCounts.get(kind) || 0).toLocaleString());
      return label;
    }));
    const byCount = [...projectCounts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    // A project keeps its colour whatever the filters, so the slot is fixed by its size in the whole brain.
    projectSlot = new Map(byCount.slice(0, SLOTS).map(([name], slot) => [name, slot]));
    const select = $('project');
    for (const [name, notes] of [...projectCounts].sort((a, b) => a[0].localeCompare(b[0]))) {
      const option = el('option', (name || 'no project') + ' (' + notes.toLocaleString() + ')');
      option.value = name;
      select.append(option);
    }
    $('tag-list').replaceChildren(...[...tags].sort().map((tag) => {
      const option = el('option');
      option.value = tag;
      return option;
    }));
    renderKey();
  }

  function renderKey() {
    const key = $('project-key');
    if ($('colour').value !== 'project') {
      key.replaceChildren();
      return;
    }
    const entries = [...projectSlot].map(([name, slot]) => [name || 'no project', theme.slots[slot]]);
    entries.push(['other projects', theme.other]);
    key.replaceChildren(...entries.map(([name, colour]) => {
      const item = el('span');
      item.append(swatch(colour), ' ' + name);
      return item;
    }));
  }

  function recolour() {
    readTheme();
    fg.backgroundColor(theme.surface);
    document.querySelectorAll('#kinds .swatch').forEach((mark, i) => { mark.style.background = theme.slots[i]; });
    renderKey();
    const selected = document.querySelector('#note-title .swatch');
    if (selected && selectedId !== null) selected.style.background = colourOf(byId.get(selectedId));
    redraw();
  }

  function start() {
    readTheme();
    const stage = $('graph');
    fg = ForceGraph()(stage)
      .nodeId('id')
      .nodeVal((node) => 1 + node.cited_by)
      .nodeRelSize(3)
      .nodeLabel(() => '')
      .nodeColor(nodeColour)
      .nodeCanvasObjectMode(() => 'after')
      .nodeCanvasObject(drawExtras)
      .linkColor(linkColour)
      .linkLineDash((link) => (link.type === 'supersedes' ? [4, 3] : null))
      .linkDirectionalArrowLength(3)
      .linkDirectionalArrowRelPos(1)
      .backgroundColor(theme.surface)
      .d3AlphaDecay(0.05)
      .warmupTicks(reducedMotion.matches ? 150 : 20)
      .cooldownTicks(reducedMotion.matches ? 0 : 200)
      .cooldownTime(6000)
      .onNodeClick((node) => select(node.id, false))
      .nodePointerAreaPaint(paintHitArea)
      .onRenderFramePost(drawLabels)
      .onNodeHover(showHover);
    stage.addEventListener('pointermove', (event) => {
      const box = stage.getBoundingClientRect();
      const card = $('hover');
      card.style.left = Math.min(event.clientX - box.left + 12, box.width - card.offsetWidth - 8) + 'px';
      card.style.top = Math.min(event.clientY - box.top + 12, box.height - card.offsetHeight - 8) + 'px';
    });
    let fitted = false;
    fg.onEngineStop(() => {
      if (!fitted && !matches && !focus) fg.zoomToFit(motionMs(300), 40);
      fitted = true;
    });
    new ResizeObserver(() => fg.width(stage.parentElement.clientWidth).height(stage.parentElement.clientHeight))
      .observe(stage.parentElement);

    buildControls();
    for (const id of ['project', 'since', 'until', 'resolved', 'superseded', 'unlinked']) $(id).addEventListener('change', render);
    $('tag').addEventListener('change', render);
    $('colour').addEventListener('change', () => { renderKey(); redraw(); });
    $('clear').addEventListener('click', clearFilters);
    $('note-close').addEventListener('click', closeNote);
    $('focus').addEventListener('click', toggleFocus);
    $('hops').addEventListener('change', () => {
      if (!focus) return;
      focus.hops = Number($('hops').value);
      render();
      fg.zoomToFit(motionMs(400), 40);
    });
    $('search-form').addEventListener('submit', (event) => { event.preventDefault(); search($('search').value); });
    $('search').addEventListener('search', () => search($('search').value));
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      if (selectedId !== null) closeNote();
      else if (matches) { $('search').value = ''; search(''); }
    });
    darkScheme.addEventListener('change', recolour);
    render();
  }

  function load(payload) {
    data = payload;
    byId = new Map(data.nodes.map((node) => [node.id, node]));
    start();
  }

  if (typeof ForceGraph !== 'function') {
    $('summary').textContent = 'The graph renderer did not load.';
    $('stage-message').textContent = 'The graph renderer did not load, so nothing can be drawn. Reload the page; if it persists, restart run_cli.py graph.';
  } else if (embedded) {
    load(JSON.parse(embedded.textContent));
  } else {
    api('graph.json').then(load).catch((error) => {
      $('summary').textContent = 'Could not load the graph.';
      $('stage-message').textContent = 'Could not load the graph (' + error.message + '). The server may have stopped, or this link is from an earlier run: start run_cli.py graph again and open the new link.';
    });
  }
})();
