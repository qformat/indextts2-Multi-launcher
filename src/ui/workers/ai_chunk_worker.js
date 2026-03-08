self.onmessage = (event) => {
  const payload = event.data || {};
  const text = String(payload.text || "");
  const maxChars = Math.max(500, Number(payload.maxChars || 4000));
  const overlapChars = Math.max(0, Number(payload.overlapChars || 200));

  const chunks = [];
  let pos = 0;
  let idx = 0;
  while (pos < text.length) {
    let end = Math.min(pos + maxChars, text.length);
    let cut = end;
    if (end < text.length) {
      const window = text.slice(pos, end);
      const start = Math.max(0, window.length - 1200);
      const part = window.slice(start);
      const seps = ["\n\n", "\n", "。", "！", "？", "；", "…", "”", '"'];
      let best = -1;
      for (const sep of seps) {
        const k = part.lastIndexOf(sep);
        if (k >= 0) {
          best = Math.max(best, start + k + sep.length);
        }
      }
      if (best > 0) {
        cut = pos + best;
      }
    }
    if (cut <= pos) cut = end;
    chunks.push({
      index: idx,
      start: pos,
      end: cut,
      text: text.slice(pos, cut),
    });
    idx += 1;
    pos = cut;
  }

  const anchors = { 旁白: 0 };
  const regex = /([^\s：:\n“”"'（）()]{1,16})[：:]/g;
  let m;
  while ((m = regex.exec(text)) !== null) {
    const name = (m[1] || "").trim();
    if (!name) continue;
    if (name.length > 12) continue;
    if (!(name in anchors)) anchors[name] = m.index;
    if (Object.keys(anchors).length >= 128) break;
  }

  const tasks = chunks.map((c, i) => {
    const prev = i > 0 ? chunks[i - 1].text.slice(-overlapChars) : "";
    return {
      chunk_index: i,
      start: c.start,
      end: c.end,
      chunk_text: c.text,
      prev_tail: prev,
      anchors: Object.entries(anchors)
        .sort((a, b) => a[1] - b[1])
        .slice(0, 24)
        .map(([name, first_pos]) => ({ name, first_pos })),
    };
  });

  self.postMessage({
    chunk_count: chunks.length,
    anchor_count: Object.keys(anchors).length,
    tasks,
  });
};
