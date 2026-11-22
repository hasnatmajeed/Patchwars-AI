// Compare source as text only. Bound the total dynamic-programming work.
const MAX_CELLS = 500000;
const MAX_EDIT_WORK = 250000;

function linesOf(text) {
  if (text === '') return [];
  const lines = text.split('\n');
  // A CR before LF is a line ending, not part of the visible line content.
  return lines.map((raw, index) => ({ raw, key: index < lines.length - 1 && raw.endsWith('\r') ? raw.slice(0, -1) : raw }));
}

// Pair occurrences of identical lines, then keep an ordered subset as anchors.
function orderedAnchors(oldLines, newLines) {
  const newPositions = new Map(), used = new Map();
  newLines.forEach((line, index) => {
    if (!newPositions.has(line.key)) newPositions.set(line.key, []);
    newPositions.get(line.key).push(index);
  });
  const candidates = [];
  oldLines.forEach((line, index) => {
    const positions = newPositions.get(line.key), count = used.get(line.key) || 0;
    if (positions && count < positions.length) {
      candidates.push({ old: index, next: positions[count] });
      used.set(line.key, count + 1);
    }
  });
  const tails = [], previous = new Int32Array(candidates.length).fill(-1);
  candidates.forEach((candidate, index) => {
    let low = 0, high = tails.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (candidates[tails[middle]].next < candidate.next) low = middle + 1;
      else high = middle;
    }
    if (low) previous[index] = tails[low - 1];
    tails[low] = index;
  });
  const anchors = [];
  let index = tails.length ? tails[tails.length - 1] : -1;
  while (index >= 0) { anchors.push(candidates[index]); index = previous[index]; }
  return anchors.reverse();
}

// Find a shortest edit script when the number of edits is modest. Stop before
// expensive comparisons and let the bounded anchor fallback handle the rest.
function boundedEditScript(oldLines, newLines) {
  const trace = [];
  let work = 0;
  const value = (frontier, diagonal, distance) => {
    const index = diagonal + distance;
    return index < 0 || index >= frontier.length ? -1 : frontier[index];
  };
  for (let distance = 0; distance <= oldLines.length + newLines.length; distance++) {
    const frontier = new Int32Array(2 * distance + 1);
    const previous = trace[distance - 1];
    for (let diagonal = -distance; diagonal <= distance; diagonal += 2) {
      if (++work > MAX_EDIT_WORK) return null;
      let x;
      if (!distance) x = 0;
      else if (diagonal === -distance || (diagonal !== distance &&
        value(previous, diagonal - 1, distance - 1) < value(previous, diagonal + 1, distance - 1))) {
        x = value(previous, diagonal + 1, distance - 1);
      } else x = value(previous, diagonal - 1, distance - 1) + 1;
      let y = x - diagonal;
      while (x < oldLines.length && y < newLines.length && oldLines[x].key === newLines[y].key) {
        if (++work > MAX_EDIT_WORK) return null;
        x++; y++;
      }
      frontier[diagonal + distance] = x;
      if (x === oldLines.length && y === newLines.length) {
        trace.push(frontier);
        const reversed = [];
        for (let d = distance; d > 0; d--) {
          const prior = trace[d - 1], k = x - y;
          const priorK = k === -d || (k !== d && value(prior, k - 1, d - 1) < value(prior, k + 1, d - 1)) ? k + 1 : k - 1;
          const priorX = value(prior, priorK, d - 1), priorY = priorX - priorK;
          while (x > priorX && y > priorY) reversed.push(['equal', oldLines[--x], newLines[--y]]);
          if (x === priorX) reversed.push(['add', null, newLines[--y]]);
          else reversed.push(['remove', oldLines[--x], null]);
        }
        while (x > 0 && y > 0) reversed.push(['equal', oldLines[--x], newLines[--y]]);
        return reversed.reverse();
      }
    }
    trace.push(frontier);
  }
  return null;
}

export function lineDiff(original, proposed) {
  const oldLines = linesOf(original), newLines = linesOf(proposed);
  const operations = [];
  let oldNumber = 1, newNumber = 1, budget = MAX_CELLS;
  let coarse = false, lineEndingsDiffer = false;
  function append(type, oldLine, newLine) {
    const display = (oldLine || newLine).key;
    if (type === 'equal' && oldLine.raw !== newLine.raw) lineEndingsDiffer = true;
    operations.push({ type, text: display, oldText: oldLine?.raw ?? null, newText: newLine?.raw ?? null,
      oldLine: oldLine ? oldNumber++ : null, newLine: newLine ? newNumber++ : null });
  }
  function compareBlock(a, b) {
    let start = 0, endA = a.length, endB = b.length;
    while (start < endA && start < endB && a[start].key === b[start].key) {
      append('equal', a[start], b[start]); start++;
    }
    while (endA > start && endB > start && a[endA - 1].key === b[endB - 1].key) { endA--; endB--; }
    const left = a.slice(start, endA), right = b.slice(start, endB);
    const cells = (left.length + 1) * (right.length + 1);
    if (!left.length) right.forEach(line => append('add', null, line));
    else if (!right.length) left.forEach(line => append('remove', line, null));
    else if (cells > budget) {
      coarse = true;
      left.forEach(line => append('remove', line, null));
      right.forEach(line => append('add', null, line));
    } else {
      budget -= cells;
      const width = right.length + 1;
      const table = new Uint32Array(cells);
      for (let i = left.length - 1; i >= 0; i--) {
        for (let j = right.length - 1; j >= 0; j--) {
          table[i * width + j] = left[i].key === right[j].key ? table[(i + 1) * width + j + 1] + 1 : Math.max(table[(i + 1) * width + j], table[i * width + j + 1]);
        }
      }
      let i = 0, j = 0;
      while (i < left.length && j < right.length) {
        if (left[i].key === right[j].key) append('equal', left[i++], right[j++]);
        else if (table[(i + 1) * width + j] >= table[i * width + j + 1]) append('remove', left[i++], null);
        else append('add', null, right[j++]);
      }
      while (i < left.length) append('remove', left[i++], null);
      while (j < right.length) append('add', null, right[j++]);
    }
    while (endA < a.length && endB < b.length) append('equal', a[endA++], b[endB++]);
  }
  if ((oldLines.length + 1) * (newLines.length + 1) <= MAX_CELLS) compareBlock(oldLines, newLines);
  else {
    const exact = boundedEditScript(oldLines, newLines);
    if (exact) {
      exact.forEach(([type, oldLine, newLine]) => append(type, oldLine, newLine));
      return { operations, coarse, lineEndingsDiffer };
    }
    // Ordered anchors keep the fallback useful, but are not guaranteed optimal.
    coarse = true;
    const anchors = orderedAnchors(oldLines, newLines);
    let oldStart = 0, newStart = 0;
    for (const anchor of anchors) {
      compareBlock(oldLines.slice(oldStart, anchor.old), newLines.slice(newStart, anchor.next));
      append('equal', oldLines[anchor.old], newLines[anchor.next]);
      oldStart = anchor.old + 1; newStart = anchor.next + 1;
    }
    compareBlock(oldLines.slice(oldStart), newLines.slice(newStart));
  }
  return { operations, coarse, lineEndingsDiffer };
}

export function splitDiffRows(operations) {
  const rows = [];
  let index = 0;
  while (index < operations.length) {
    if (operations[index].type === 'equal') {
      rows.push({ left: operations[index], right: operations[index] });
      index++;
      continue;
    }
    const removed = [], added = [];
    while (index < operations.length && operations[index].type !== 'equal') {
      const item = operations[index++];
      (item.type === 'remove' ? removed : added).push(item);
    }
    for (let i = 0; i < Math.max(removed.length, added.length); i++) rows.push({ left: removed[i] || null, right: added[i] || null });
  }
  return rows;
}
