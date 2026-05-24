import { formatNumber, formatPercent, isFiniteNumber, showToast } from "./ui.js";

const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
const STORAGE_PREFIX = "ihsg-chart-drawings-v1";
const SETTINGS_KEY = "ihsg-chart-drawing-settings-v1";
const DEFAULT_STYLE = {
  color: "#22d3ee",
  lineWidth: 2,
  lineStyle: "solid",
};
const REQUIRED_POINTS = {
  trendline: 2,
  ray: 2,
  channel: 3,
  fibonacci: 2,
  rectangle: 2,
  text: 1,
  arrow: 2,
  measure: 2,
  zoom: 2,
};
const TOOL_HELP = {
  select: "Select: click a drawing, then drag to move it.",
  crosshair: "Crosshair: hover the candle chart for OHLCV details.",
  trendline: "Trend line: click the first point, then click the second point.",
  horizontal: "Horizontal line: click one price level.",
  vertical: "Vertical line: click one date/time.",
  ray: "Ray line: click two points. The line extends to the right.",
  channel: "Parallel channel: click a base line, then click the channel width.",
  fibonacci: "Fibonacci: click swing start and swing end.",
  rectangle: "Rectangle: drag an area, or click two opposite corners.",
  brush: "Brush: drag to draw freehand, or click to place a dot.",
  text: "Text: click the chart, type, then press Enter.",
  arrow: "Arrow: click start and end points.",
  measure: "Measure: click start and end points.",
  zoom: "Zoom: drag an area, or click two corners. Double click resets.",
  delete: "Delete: click a drawing to remove it, or select one and press Delete.",
};

export class DrawingLayer {
  constructor({ svg, host, tooltipNode, toast = showToast }) {
    this.svg = svg;
    this.host = host;
    this.tooltipNode = tooltipNode;
    this.toast = toast;
    this.chart = null;
    this.candleSeries = null;
    this.ticker = "BBCA";
    this.candles = [];
    this.drawings = [];
    this.selectedId = null;
    this.activeTool = "crosshair";
    this.pending = null;
    this.preview = null;
    this.pointerState = null;
    this.undoStack = [];
    this.redoStack = [];
    this.settings = this.loadSettings();
    this.resizeObserver = new ResizeObserver(() => this.render());

    this.createSettingsPanel();
    this.createStatusPanel();
    this.bindEvents();
  }

  attach({ chart, candleSeries, ticker, candles }) {
    this.chart = chart;
    this.candleSeries = candleSeries;
    this.resizeObserver.observe(this.host);
    if (this.chart?.timeScale?.().subscribeVisibleTimeRangeChange) {
      this.chart.timeScale().subscribeVisibleTimeRangeChange(() => this.render());
    }
    if (this.chart?.timeScale?.().subscribeVisibleLogicalRangeChange) {
      this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => this.render());
    }
    this.setTicker(ticker, candles);
  }

  setTicker(ticker, candles = []) {
    this.closeTextEditor(false);
    if (this.ticker) this.saveDrawings();
    this.ticker = normalizeTicker(ticker);
    this.candles = normalizeCandles(candles);
    this.drawings = this.loadDrawings(this.ticker);
    this.selectedId = null;
    this.pending = null;
    this.preview = null;
    this.undoStack = [];
    this.redoStack = [];
    this.render();
  }

  updateCandles(candles = []) {
    this.candles = normalizeCandles(candles);
    this.render();
  }

  setTool(toolId) {
    this.closeTextEditor(true);
    this.activeTool = toolId;
    this.pending = null;
    this.preview = null;
    if (!["select", "delete"].includes(toolId)) this.selectedId = null;
    this.svg.classList.toggle("drawing-passive", toolId === "crosshair");
    this.svg.dataset.tool = toolId;
    this.setStatus(TOOL_HELP[toolId] || "");
    this.render();
  }

  setMagnet(enabled) {
    this.settings.magnet = Boolean(enabled);
    this.saveSettings();
    this.setStatus(`Magnet mode ${enabled ? "on" : "off"}. Points ${enabled ? "snap to nearest close" : "use exact cursor price"}.`);
    this.render();
  }

  setGlobalLock(enabled) {
    this.settings.lockAll = Boolean(enabled);
    this.saveSettings();
    this.setStatus(`Drawing lock ${enabled ? "on" : "off"}.`);
    this.render();
  }

  setHidden(enabled) {
    this.settings.hidden = Boolean(enabled);
    this.saveSettings();
    this.setStatus(`Drawings are ${enabled ? "hidden" : "visible"}.`);
    this.render();
  }

  saveDrawings() {
    try {
      window.localStorage.setItem(this.storageKey(this.ticker), JSON.stringify(this.drawings));
      return true;
    } catch (error) {
      this.toast(`Drawing save failed: ${error.message}`, "error");
      return false;
    }
  }

  clearDrawings() {
    if (!window.confirm(`Clear all drawings for ${this.ticker}?`)) return false;
    this.pushHistory();
    this.drawings = [];
    this.selectedId = null;
    this.pending = null;
    this.preview = null;
    this.saveDrawings();
    this.render();
    this.toast(`Drawings cleared for ${this.ticker}`);
    this.setStatus(`Drawings cleared for ${this.ticker}.`);
    return true;
  }

  deleteSelected() {
    if (!this.selectedId) return false;
    return this.deleteDrawing(this.selectedId);
  }

  undo() {
    if (!this.undoStack.length) return false;
    this.redoStack.push(clone(this.drawings));
    this.drawings = this.undoStack.pop();
    this.selectedId = null;
    this.saveDrawings();
    this.render();
    return true;
  }

  redo() {
    if (!this.redoStack.length) return false;
    this.undoStack.push(clone(this.drawings));
    this.drawings = this.redoStack.pop();
    this.selectedId = null;
    this.saveDrawings();
    this.render();
    return true;
  }

  getSelectedDrawing() {
    return this.drawings.find((drawing) => drawing.id === this.selectedId) || null;
  }

  bindEvents() {
    this.svg.addEventListener("pointerdown", (event) => this.handlePointerDown(event));
    this.svg.addEventListener("pointermove", (event) => this.handlePointerMove(event));
    this.svg.addEventListener("pointerup", (event) => this.handlePointerUp(event));
    this.svg.addEventListener("pointercancel", () => this.cancelPointer());
    this.svg.addEventListener("dblclick", (event) => {
      if (this.activeTool === "zoom") {
        event.preventDefault();
        this.chart?.timeScale().fitContent();
      }
    });
  }

  handlePointerDown(event) {
    if (!this.chart || !this.candleSeries || this.activeTool === "crosshair") return;
    event.preventDefault();

    const targetId = this.eventDrawingId(event);
    const screen = this.eventToScreen(event);
    const point = this.screenToPoint(screen);
    if (!point) return;

    this.svg.setPointerCapture?.(event.pointerId);

    if (this.activeTool === "select") {
      this.selectDrawing(targetId);
      const selected = this.getSelectedDrawing();
      if (selected && !this.isLocked(selected)) {
        this.pushHistory();
        this.pointerState = {
          mode: "move",
          pointerId: event.pointerId,
          startScreen: screen,
          original: clone(selected),
          id: selected.id,
        };
      } else {
        this.pointerState = { mode: "click", pointerId: event.pointerId, startScreen: screen, point, targetId };
      }
      return;
    }

    if (this.activeTool === "delete") {
      if (targetId) this.deleteDrawing(targetId);
      else if (!this.deleteSelected()) this.setStatus("Delete: click a drawing first.");
      return;
    }

    if (this.activeTool === "brush") {
      this.pointerState = { mode: "brush", pointerId: event.pointerId, points: [point] };
      this.preview = this.makeDrawing("brush", [point], { path: [point] });
      this.render();
      return;
    }

    if (["rectangle", "zoom"].includes(this.activeTool)) {
      this.pointerState = {
        mode: this.activeTool,
        pointerId: event.pointerId,
        startScreen: screen,
        startPoint: point,
      };
      this.preview = this.makeDrawing(this.activeTool, [point, point]);
      this.render();
      return;
    }

    this.pointerState = { mode: "click", pointerId: event.pointerId, startScreen: screen, point, targetId };
  }

  handlePointerMove(event) {
    if (!this.pointerState || this.pointerState.pointerId !== event.pointerId) {
      this.updatePreview(event);
      return;
    }

    const screen = this.eventToScreen(event);
    const point = this.screenToPoint(screen);
    if (!point) return;

    if (this.pointerState.mode === "move") {
      this.moveDrawing(this.pointerState, screen);
      return;
    }

    if (this.pointerState.mode === "brush") {
      const points = this.pointerState.points;
      const previous = points[points.length - 1];
      if (!previous || distance(this.pointToScreen(previous), screen) > 4) {
        points.push(point);
        this.preview = this.makeDrawing("brush", points, { path: points });
        this.render();
      }
      return;
    }

    if (this.pointerState.mode === "rectangle" || this.pointerState.mode === "zoom") {
      this.preview = this.makeDrawing(this.pointerState.mode, [this.pointerState.startPoint, point]);
      this.render();
    }
  }

  handlePointerUp(event) {
    if (!this.pointerState || this.pointerState.pointerId !== event.pointerId) return;
    const state = this.pointerState;
    const screen = this.eventToScreen(event);
    const point = this.screenToPoint(screen);
    this.pointerState = null;
    this.svg.releasePointerCapture?.(event.pointerId);

    if (state.mode === "move") {
      this.saveDrawings();
      this.render();
      return;
    }

    if (state.mode === "brush") {
      this.preview = null;
      if (state.points.length >= 1) {
        this.addDrawing(this.makeDrawing("brush", state.points, { path: state.points }));
      } else {
        this.render();
      }
      return;
    }

    if (state.mode === "rectangle" && point) {
      this.preview = null;
      if (distance(this.pointToScreen(state.startPoint), screen) > 8) {
        this.addDrawing(this.makeDrawing("rectangle", [state.startPoint, point]));
      } else {
        this.handleToolClick(point, state.targetId);
      }
      return;
    }

    if (state.mode === "zoom" && point) {
      this.preview = null;
      if (distance(this.pointToScreen(state.startPoint), screen) > 8) {
        this.zoomToPoints(state.startPoint, point);
        this.render();
      } else {
        this.handleToolClick(point, state.targetId);
      }
      return;
    }

    if (state.mode === "click" && point && distance(state.startScreen, screen) < 6) {
      this.handleToolClick(point, state.targetId);
    }
  }

  cancelPointer() {
    this.pointerState = null;
    this.preview = null;
    this.render();
  }

  handleToolClick(point, targetId) {
    if (this.activeTool === "select") {
      this.selectDrawing(targetId);
      return;
    }

    if (this.settings.lockAll && targetId) return;

    if (this.activeTool === "horizontal") {
      this.addDrawing(this.makeDrawing("horizontal", [point]));
      return;
    }
    if (this.activeTool === "vertical") {
      this.addDrawing(this.makeDrawing("vertical", [point]));
      return;
    }
    if (this.activeTool === "text") {
      this.openTextEditor(point);
      return;
    }

    const requiredPoints = REQUIRED_POINTS[this.activeTool];
    if (!requiredPoints) return;

    if (!this.pending || this.pending.type !== this.activeTool) {
      this.pending = { type: this.activeTool, points: [] };
    }
    this.pending.points.push(point);
    if (this.pending.points.length >= requiredPoints) {
      const drawing = this.makeDrawing(this.activeTool, this.pending.points);
      this.pending = null;
      this.preview = null;
      if (this.activeTool === "zoom") {
        this.zoomToPoints(drawing.points[0], drawing.points[1]);
        this.setStatus("Zoom applied. Double click the chart or use Reset Zoom to fit content.");
        this.render();
        return;
      }
      this.addDrawing(drawing);
    } else {
      this.preview = this.makeDrawing(this.activeTool, [...this.pending.points, point]);
      this.setPendingStatus();
      this.render();
    }
  }

  updatePreview(event) {
    if (!this.pending?.points?.length || this.activeTool === "crosshair") return;
    const point = this.screenToPoint(this.eventToScreen(event));
    if (!point) return;
    this.preview = this.makeDrawing(this.pending.type, [...this.pending.points, point]);
    this.render();
  }

  makeDrawing(type, points, extra = {}) {
    return {
      id: extra.id || `drawing_${Date.now()}_${Math.round(Math.random() * 100000)}`,
      ticker: this.ticker,
      type,
      points: points.map((point) => ({ time: normalizeTime(point.time), price: Number(point.price) })),
      path: extra.path?.map((point) => ({ time: normalizeTime(point.time), price: Number(point.price) })),
      text: extra.text || "",
      style: { ...DEFAULT_STYLE, ...(extra.style || {}) },
      visible: extra.visible !== false,
      locked: Boolean(extra.locked),
      createdAt: extra.createdAt || new Date().toISOString(),
    };
  }

  addDrawing(drawing) {
    this.pushHistory();
    this.drawings.push(drawing);
    this.selectedId = drawing.id;
    this.saveDrawings();
    this.setStatus(`${toolLabel(drawing.type)} added for ${this.ticker}.`);
    this.render();
  }

  deleteDrawing(id) {
    const drawing = this.drawings.find((item) => item.id === id);
    if (!drawing || this.isLocked(drawing)) return false;
    this.pushHistory();
    this.drawings = this.drawings.filter((item) => item.id !== id);
    if (this.selectedId === id) this.selectedId = null;
    this.saveDrawings();
    this.setStatus(`${toolLabel(drawing.type)} deleted.`);
    this.render();
    return true;
  }

  duplicateSelected() {
    const selected = this.getSelectedDrawing();
    if (!selected) return;
    const copy = clone(selected);
    copy.id = `drawing_${Date.now()}_${Math.round(Math.random() * 100000)}`;
    copy.createdAt = new Date().toISOString();
    copy.points = copy.points.map((point) => this.offsetPoint(point, 18, -18));
    if (copy.path) copy.path = copy.path.map((point) => this.offsetPoint(point, 18, -18));
    this.addDrawing(copy);
  }

  selectDrawing(id) {
    this.selectedId = id || null;
    this.setStatus(id ? "Drawing selected. Drag to move, or use the settings panel." : TOOL_HELP.select);
    this.render();
  }

  moveDrawing(state, currentScreen) {
    const drawing = this.drawings.find((item) => item.id === state.id);
    if (!drawing) return;
    const dx = currentScreen.x - state.startScreen.x;
    const dy = currentScreen.y - state.startScreen.y;

    drawing.points = state.original.points.map((point) =>
      this.movePointForDrawing(state.original.type, point, dx, dy),
    );
    if (state.original.path) {
      drawing.path = state.original.path.map((point) => this.movePointForDrawing(state.original.type, point, dx, dy));
    }
    this.render();
  }

  movePointForDrawing(type, point, dx, dy) {
    const screen = this.pointToScreen(point);
    if (!screen) return point;
    const moved = { x: screen.x + dx, y: screen.y + dy };
    const next = this.screenToPoint(moved, { snap: false }) || point;
    if (type === "horizontal") return { ...point, price: next.price };
    if (type === "vertical") return { ...point, time: next.time };
    return next;
  }

  offsetPoint(point, dx, dy) {
    const screen = this.pointToScreen(point);
    if (!screen) return point;
    return this.screenToPoint({ x: screen.x + dx, y: screen.y + dy }, { snap: false }) || point;
  }

  zoomToPoints(first, second) {
    const start = Math.min(normalizeTime(first.time), normalizeTime(second.time));
    const end = Math.max(normalizeTime(first.time), normalizeTime(second.time));
    if (start && end && end > start) {
      this.chart.timeScale().setVisibleRange({ from: start, to: end });
      this.setStatus("Zoom applied. Use Reset Zoom or Ctrl+0 to fit content.");
    }
  }

  pushHistory() {
    this.undoStack.push(clone(this.drawings));
    if (this.undoStack.length > 50) this.undoStack.shift();
    this.redoStack = [];
  }

  isLocked(drawing) {
    return this.settings.lockAll || drawing?.locked;
  }

  eventDrawingId(event) {
    return event.target.closest?.("[data-drawing-id]")?.dataset?.drawingId || null;
  }

  eventToScreen(event) {
    const rect = this.svg.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  }

  screenToPoint(screen, { snap = true } = {}) {
    if (!this.chart || !this.candleSeries) return null;
    let time = normalizeTime(this.chart.timeScale().coordinateToTime(screen.x));
    if (!time) time = this.nearestTimeByCoordinate(screen.x);
    const price = this.candleSeries.coordinateToPrice(screen.y);
    if (!time || !isFiniteNumber(price)) return null;
    const point = { time, price: Number(price) };
    return snap && this.settings.magnet ? this.snapPoint(point) : point;
  }

  pointToScreen(point) {
    if (!this.chart || !this.candleSeries || !point) return null;
    const x = this.chart.timeScale().timeToCoordinate(normalizeTime(point.time));
    const y = this.candleSeries.priceToCoordinate(Number(point.price));
    if (!isFiniteNumber(x) || !isFiniteNumber(y)) return null;
    return { x: Number(x), y: Number(y) };
  }

  nearestTimeByCoordinate(x) {
    if (!this.candles.length) return null;
    let best = this.candles[0];
    let bestDistance = Number.POSITIVE_INFINITY;
    for (const candle of this.candles) {
      const coordinate = this.chart.timeScale().timeToCoordinate(candle.time);
      if (!isFiniteNumber(coordinate)) continue;
      const currentDistance = Math.abs(Number(coordinate) - x);
      if (currentDistance < bestDistance) {
        best = candle;
        bestDistance = currentDistance;
      }
    }
    return best?.time || null;
  }

  snapPoint(point) {
    if (!this.candles.length) return point;
    let best = this.candles[0];
    let bestDistance = Math.abs(best.time - point.time);
    for (const candle of this.candles) {
      const currentDistance = Math.abs(candle.time - point.time);
      if (currentDistance < bestDistance) {
        best = candle;
        bestDistance = currentDistance;
      }
    }
    return { time: best.time, price: best.close };
  }

  render() {
    if (!this.svg) return;
    const visibleDrawings = this.settings.hidden ? [] : this.drawings.filter((drawing) => drawing.visible !== false);
    const previewMarkup = this.preview ? this.renderDrawing(this.preview, { preview: true }) : "";
    this.svg.innerHTML = `${this.svgDefs()}${visibleDrawings.map((drawing) => this.renderDrawing(drawing)).join("")}${previewMarkup}`;
    this.updateSettingsPanel();
  }

  renderDrawing(drawing, { preview = false } = {}) {
    const style = drawing.style || DEFAULT_STYLE;
    const className = [
      "drawing-object",
      `drawing-${drawing.type}`,
      preview ? "is-preview" : "",
      drawing.id === this.selectedId ? "is-selected" : "",
      this.isLocked(drawing) ? "is-locked" : "",
    ]
      .filter(Boolean)
      .join(" ");
    const body = this.drawingBody(drawing, preview);
    if (!body) return "";
    const data = preview ? "" : ` data-drawing-id="${escapeHtml(drawing.id)}"`;
    return `<g class="${className}"${data}>${body}${!preview && drawing.id === this.selectedId ? this.handleMarkup(drawing) : ""}</g>`;
  }

  drawingBody(drawing, preview) {
    const style = drawing.style || DEFAULT_STYLE;
    const color = escapeHtml(style.color || DEFAULT_STYLE.color);
    const width = Number(style.lineWidth || DEFAULT_STYLE.lineWidth);
    const dash = dashArray(style.lineStyle);
    const attrs = `stroke="${color}" stroke-width="${width}" stroke-dasharray="${dash}"`;

    if (drawing.type === "horizontal") {
      const y = this.candleSeries?.priceToCoordinate(drawing.points[0]?.price);
      if (!isFiniteNumber(y)) return "";
      return `<line class="drawing-hit" x1="0" y1="${y}" x2="100%" y2="${y}" />` +
        `<line ${attrs} x1="0" y1="${y}" x2="100%" y2="${y}" />` +
        this.labelAt(8, Number(y) - 8, formatNumber(drawing.points[0].price), color);
    }

    if (drawing.type === "vertical") {
      const x = this.chart?.timeScale().timeToCoordinate(drawing.points[0]?.time);
      if (!isFiniteNumber(x)) return "";
      return `<line class="drawing-hit" x1="${x}" y1="0" x2="${x}" y2="100%" />` +
        `<line ${attrs} x1="${x}" y1="0" x2="${x}" y2="100%" />`;
    }

    if (drawing.type === "brush") {
      const points = (drawing.path || drawing.points).map((point) => this.pointToScreen(point)).filter(Boolean);
      if (points.length === 1) {
        const point = points[0];
        return `<circle ${attrs} cx="${point.x}" cy="${point.y}" r="${Math.max(width + 1, 3)}" fill="${color}" />`;
      }
      if (points.length < 2) return "";
      const d = points.map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`).join(" ");
      return `<path class="drawing-hit" d="${d}" />` + `<path ${attrs} d="${d}" fill="none" />`;
    }

    if (drawing.type === "text") {
      const point = this.pointToScreen(drawing.points[0]);
      if (!point) return "";
      return `<text x="${point.x}" y="${point.y}" fill="${color}" class="drawing-text">${escapeHtml(drawing.text || "Text")}</text>`;
    }

    if (drawing.type === "rectangle" || drawing.type === "zoom") {
      const first = this.pointToScreen(drawing.points[0]);
      const second = this.pointToScreen(drawing.points[1]);
      if (!first || !second) return "";
      const x = Math.min(first.x, second.x);
      const y = Math.min(first.y, second.y);
      const w = Math.abs(first.x - second.x);
      const h = Math.abs(first.y - second.y);
      return `<rect class="drawing-hit" x="${x}" y="${y}" width="${w}" height="${h}" />` +
        `<rect ${attrs} x="${x}" y="${y}" width="${w}" height="${h}" fill="${preview && drawing.type === "zoom" ? "rgba(114,198,255,0.16)" : "rgba(34,211,238,0.1)"}" />`;
    }

    if (drawing.type === "fibonacci") {
      const first = this.pointToScreen(drawing.points[0]);
      const second = this.pointToScreen(drawing.points[1]);
      if (!first || !second) return "";
      const left = Math.min(first.x, second.x);
      const right = Math.max(first.x, second.x);
      const high = Number(drawing.points[0].price);
      const low = Number(drawing.points[1].price);
      return FIB_LEVELS.map((level) => {
        const price = high + (low - high) * level;
        const y = this.candleSeries.priceToCoordinate(price);
        if (!isFiniteNumber(y)) return "";
        return `<line class="drawing-hit" x1="${left}" y1="${y}" x2="${right}" y2="${y}" />` +
          `<line ${attrs} x1="${left}" y1="${y}" x2="${right}" y2="${y}" />` +
          this.labelAt(right + 6, Number(y) - 4, `${level} ${formatNumber(price)}`, color);
      }).join("");
    }

    if (drawing.type === "channel") {
      const points = drawing.points.map((point) => this.pointToScreen(point));
      if (points.length < 2 || points.some((point) => !point)) return "";
      const [a, b, c] = points;
      if (!c) {
        return `<line class="drawing-hit" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" />` +
          `<line ${attrs} x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" />` +
          this.labelAt(b.x + 8, b.y - 8, "click channel width", color);
      }
      const offset = { x: c.x - a.x, y: c.y - a.y };
      const d = { x: b.x + offset.x, y: b.y + offset.y };
      return `<polygon points="${a.x},${a.y} ${b.x},${b.y} ${d.x},${d.y} ${c.x},${c.y}" fill="rgba(34,211,238,0.08)" />` +
        `<line class="drawing-hit" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" />` +
        `<line class="drawing-hit" x1="${c.x}" y1="${c.y}" x2="${d.x}" y2="${d.y}" />` +
        `<line ${attrs} x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" />` +
        `<line ${attrs} x1="${c.x}" y1="${c.y}" x2="${d.x}" y2="${d.y}" />`;
    }

    const points = drawing.points.map((point) => this.pointToScreen(point));
    if (points.length < 2 || points.some((point) => !point)) return "";
    const [first, second] = points;
    if (drawing.type === "ray") {
      const right = this.svg.clientWidth || this.host.clientWidth;
      const slope = (second.y - first.y) / Math.max(second.x - first.x, 1);
      const end = { x: right, y: first.y + slope * (right - first.x) };
      return `<line class="drawing-hit" x1="${first.x}" y1="${first.y}" x2="${end.x}" y2="${end.y}" />` +
        `<line ${attrs} x1="${first.x}" y1="${first.y}" x2="${end.x}" y2="${end.y}" />`;
    }
    if (drawing.type === "arrow") {
      return `<line class="drawing-hit" x1="${first.x}" y1="${first.y}" x2="${second.x}" y2="${second.y}" />` +
        `<line ${attrs} x1="${first.x}" y1="${first.y}" x2="${second.x}" y2="${second.y}" marker-end="url(#drawing-arrow)" />`;
    }
    if (drawing.type === "measure") {
      const details = this.measureLabel(drawing.points[0], drawing.points[1]);
      const mid = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
      return `<line class="drawing-hit" x1="${first.x}" y1="${first.y}" x2="${second.x}" y2="${second.y}" />` +
        `<line ${attrs} x1="${first.x}" y1="${first.y}" x2="${second.x}" y2="${second.y}" />` +
        this.labelAt(mid.x + 8, mid.y - 8, details, color);
    }
    return `<line class="drawing-hit" x1="${first.x}" y1="${first.y}" x2="${second.x}" y2="${second.y}" />` +
      `<line ${attrs} x1="${first.x}" y1="${first.y}" x2="${second.x}" y2="${second.y}" />`;
  }

  handleMarkup(drawing) {
    return drawing.points
      .map((point) => this.pointToScreen(point))
      .filter(Boolean)
      .map((point) => `<circle class="drawing-handle" cx="${point.x}" cy="${point.y}" r="4" />`)
      .join("");
  }

  labelAt(x, y, text, color) {
    return `<text class="drawing-label" x="${x}" y="${y}" fill="${color}">${escapeHtml(text)}</text>`;
  }

  measureLabel(first, second) {
    const diff = Number(second.price) - Number(first.price);
    const pct = Number(first.price) ? diff / Number(first.price) : null;
    const from = Math.min(first.time, second.time);
    const to = Math.max(first.time, second.time);
    const bars = this.candles.filter((candle) => candle.time >= from && candle.time <= to).length;
    return `${formatNumber(diff)} | ${formatPercent(pct)} | ${bars} bars`;
  }

  svgDefs() {
    return `<defs><marker id="drawing-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#22d3ee" /></marker></defs>`;
  }

  createSettingsPanel() {
    this.settingsPanel = document.createElement("div");
    this.settingsPanel.className = "drawing-settings-panel hidden";
    this.settingsPanel.innerHTML = `
      <label>Color <input type="color" data-setting="color" value="${DEFAULT_STYLE.color}"></label>
      <label>Width <input type="number" min="1" max="8" step="1" data-setting="lineWidth" value="2"></label>
      <label>Style
        <select data-setting="lineStyle">
          <option value="solid">Solid</option>
          <option value="dashed">Dashed</option>
          <option value="dotted">Dotted</option>
        </select>
      </label>
      <div class="drawing-settings-actions">
        <button type="button" data-action="duplicate">Duplicate</button>
        <button type="button" data-action="lock">Lock</button>
        <button type="button" data-action="delete">Delete</button>
      </div>
    `;
    this.host.appendChild(this.settingsPanel);
    this.settingsPanel.addEventListener("input", (event) => this.handleSettingInput(event));
    this.settingsPanel.addEventListener("change", (event) => this.handleSettingInput(event));
    this.settingsPanel.addEventListener("click", (event) => this.handleSettingAction(event));
  }

  createStatusPanel() {
    this.statusNode = document.createElement("div");
    this.statusNode.className = "drawing-tool-status hidden";
    this.host.appendChild(this.statusNode);
  }

  setStatus(message) {
    if (!this.statusNode) return;
    this.statusNode.textContent = message || "";
    this.statusNode.classList.toggle("hidden", !message);
  }

  setPendingStatus() {
    if (!this.pending) return;
    const required = REQUIRED_POINTS[this.pending.type] || 0;
    const current = this.pending.points.length;
    const next = Math.max(required - current, 0);
    this.setStatus(`${toolLabel(this.pending.type)}: ${current}/${required} points set. Click ${next} more point${next === 1 ? "" : "s"}.`);
  }

  openTextEditor(point) {
    this.closeTextEditor(false);
    const screen = this.pointToScreen(point);
    if (!screen) return;
    const input = document.createElement("input");
    input.className = "drawing-text-editor";
    input.type = "text";
    input.placeholder = "Type annotation";
    input.style.left = `${Math.min(screen.x + 8, this.host.clientWidth - 260)}px`;
    input.style.top = `${Math.max(8, screen.y - 18)}px`;
    this.host.appendChild(input);
    this.textEditor = { input, point, committed: false };
    this.setStatus("Text: type annotation, Enter to save, Esc to cancel.");

    const commit = () => {
      if (!this.textEditor || this.textEditor.committed) return;
      this.textEditor.committed = true;
      const text = input.value.trim();
      input.remove();
      this.textEditor = null;
      if (text) this.addDrawing(this.makeDrawing("text", [point], { text }));
      else this.setStatus("Text cancelled.");
    };
    const cancel = () => {
      if (!this.textEditor || this.textEditor.committed) return;
      this.textEditor.committed = true;
      input.remove();
      this.textEditor = null;
      this.setStatus("Text cancelled.");
    };
    input.addEventListener("keydown", (event) => {
      event.stopPropagation();
      if (event.key === "Enter") commit();
      if (event.key === "Escape") cancel();
    });
    input.addEventListener("blur", commit);
    window.setTimeout(() => input.focus(), 0);
  }

  closeTextEditor(shouldCommit) {
    if (!this.textEditor) return;
    if (shouldCommit) {
      this.textEditor.input.blur();
      return;
    }
    this.textEditor.input.remove();
    this.textEditor = null;
  }

  handleSettingInput(event) {
    const selected = this.getSelectedDrawing();
    const setting = event.target.dataset.setting;
    if (!selected || !setting || this.isLocked(selected)) return;
    this.pushHistory();
    selected.style = { ...DEFAULT_STYLE, ...(selected.style || {}) };
    selected.style[setting] = setting === "lineWidth" ? Number(event.target.value) : event.target.value;
    this.saveDrawings();
    this.render();
  }

  handleSettingAction(event) {
    const action = event.target.closest("button")?.dataset.action;
    if (!action) return;
    if (action === "delete") this.deleteSelected();
    if (action === "duplicate") this.duplicateSelected();
    if (action === "lock") {
      const selected = this.getSelectedDrawing();
      if (!selected) return;
      this.pushHistory();
      selected.locked = !selected.locked;
      this.saveDrawings();
      this.render();
    }
  }

  updateSettingsPanel() {
    const selected = this.getSelectedDrawing();
    if (!selected || this.settings.hidden || this.activeTool !== "select") {
      this.settingsPanel.classList.add("hidden");
      return;
    }
    const point = this.pointToScreen(selected.points[0]);
    if (!point) {
      this.settingsPanel.classList.add("hidden");
      return;
    }
    const style = { ...DEFAULT_STYLE, ...(selected.style || {}) };
    this.settingsPanel.querySelector('[data-setting="color"]').value = style.color;
    this.settingsPanel.querySelector('[data-setting="lineWidth"]').value = style.lineWidth;
    this.settingsPanel.querySelector('[data-setting="lineStyle"]').value = style.lineStyle;
    this.settingsPanel.querySelector('[data-action="lock"]').textContent = selected.locked ? "Unlock" : "Lock";
    this.settingsPanel.style.left = `${Math.min(point.x + 14, this.host.clientWidth - 230)}px`;
    this.settingsPanel.style.top = `${Math.max(12, point.y + 14)}px`;
    this.settingsPanel.classList.remove("hidden");
  }

  loadDrawings(ticker) {
    try {
      const raw = window.localStorage.getItem(this.storageKey(ticker));
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) throw new Error("Drawing payload is not an array.");
      return parsed.filter((drawing) => drawing?.id && drawing?.type && Array.isArray(drawing.points));
    } catch (error) {
      window.localStorage.removeItem(this.storageKey(ticker));
      this.toast(`Drawing storage for ${ticker} was reset: ${error.message}`, "error");
      return [];
    }
  }

  loadSettings() {
    try {
      return {
        magnet: false,
        lockAll: false,
        hidden: false,
        ...(JSON.parse(window.localStorage.getItem(SETTINGS_KEY) || "{}") || {}),
      };
    } catch {
      window.localStorage.removeItem(SETTINGS_KEY);
      return { magnet: false, lockAll: false, hidden: false };
    }
  }

  saveSettings() {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(this.settings));
  }

  storageKey(ticker) {
    return `${STORAGE_PREFIX}:${normalizeTicker(ticker)}`;
  }
}

function toolLabel(type) {
  return String(type || "Drawing")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function normalizeTicker(ticker) {
  return String(ticker || "BBCA").toUpperCase().replace(".JK", "");
}

function normalizeCandles(rows) {
  return (rows || [])
    .map((row) => ({
      ...row,
      time: normalizeTime(row.time || row.date),
      close: Number(row.close),
    }))
    .filter((row) => row.time && isFiniteNumber(row.close))
    .sort((a, b) => a.time - b.time);
}

function normalizeTime(value) {
  if (!value) return null;
  if (typeof value === "number") return Math.floor(value);
  if (typeof value === "object" && value.year && value.month && value.day) {
    return Math.floor(Date.UTC(value.year, value.month - 1, value.day) / 1000);
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : null;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function distance(first, second) {
  if (!first || !second) return 0;
  return Math.hypot(first.x - second.x, first.y - second.y);
}

function dashArray(style) {
  if (style === "dashed") return "8 5";
  if (style === "dotted") return "2 5";
  return "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
