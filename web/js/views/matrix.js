/* MatrixView: a payoff table for simultaneous-move games.
 *
 * Part: {view: "matrix", rowLabels, colLabels, payoffs: [[[row, col]]],
 *        rowPlayer, colPlayer, rowActions, highlight: [r, c], history} */

import { h } from '../dom.js';
import { View } from './view.js';

export class MatrixView extends View {
  static type = 'matrix';

  render(part) {
    const hi = part.highlight;
    const table = h('table.payoff');
    const head = h('tr', h('th.corner', h('span.rowname', this.name(part.rowPlayer)),
      h('span.colname', this.name(part.colPlayer))));
    part.colLabels.forEach((c, j) => head.append(h('th.col', { class: hi && hi[1] === j ? 'hit' : '' }, c)));
    table.append(h('thead', head));
    const body = h('tbody');
    part.rowLabels.forEach((r, i) => {
      const th = h('th.rowhead', { class: hi && hi[0] === i ? 'hit' : '' }, r);
      this.actionable(th, part.rowActions?.[i]);
      const tr = h('tr', th);
      part.colLabels.forEach((_, j) => {
        const [a, b] = part.payoffs[i][j];
        const td = h('td.pay', { class: hi && hi[0] === i && hi[1] === j ? 'hit' : '' },
          h('span.pay-row', { style: { color: this.color(part.rowPlayer) } }, fmtPay(a)),
          h('span.pay-col', { style: { color: this.color(part.colPlayer) } }, fmtPay(b)));
        tr.append(td);
      });
      body.append(tr);
    });
    table.append(body);
    this.el.append(table);
    if (part.history?.length) {
      const strip = h('div.matrix-history');
      part.history.forEach(([i, j], k) => strip.append(h('span.chip', `${k + 1}: ${part.rowLabels[i]} / ${part.colLabels[j]}`)));
      this.el.append(strip);
    }
  }
}

function fmtPay(x) { return Number.isInteger(x) ? String(x) : x.toFixed(1); }
