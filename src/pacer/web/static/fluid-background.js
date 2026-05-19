/**
 * Ink Brush Background — mouse as calligraphy brush.
 *
 * Blank canvas. When the mouse moves, it leaves ink-like particles
 * that slowly spread outward and fade, like wet ink bleeding into rice paper.
 * No mouse = empty, quiet, blank.
 */
class FluidBackground {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = null;
    this.particles = [];        // alive particles
    this.maxParticles = 400;
    this.mouse = { x: -1, y: -1, prevX: -1, prevY: -1, active: false };
    this._lastSpawn = 0;
    this.rafId = null;
    this._init();
  }

  _init() {
    const gl = this.canvas.getContext('webgl', {
      alpha: true, antialias: false, premultipliedAlpha: false,
      powerPreference: 'high-performance',
    });
    if (!gl) { console.warn('WebGL not available'); return; }
    this.gl = gl;
    this._resize();
    if (!this._buildProgram()) return;
    this._bindEvents();
    this._loop();
  }

  _resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = this.canvas.clientWidth * dpr;
    const h = this.canvas.clientHeight * dpr;
    if (this.canvas.width === w && this.canvas.height === h) return;
    this.canvas.width = w;
    this.canvas.height = h;
    if (this.gl) this.gl.viewport(0, 0, w, h);
  }

  _compile(gl, type, src) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.warn('shader error:', gl.getShaderInfoLog(s));
      gl.deleteShader(s);
      return null;
    }
    return s;
  }

  _buildProgram() {
    const gl = this.gl;

    const vs = this._compile(gl, gl.VERTEX_SHADER, `
      precision highp float;
      attribute vec2 aPos;
      attribute float aSize;
      attribute float aAlpha;
      uniform vec2 uRes;
      uniform float uPtScale;
      varying float vAlpha;
      void main() {
        vec2 ndc = aPos * 2.0 - 1.0;
        gl_Position = vec4(ndc.x, ndc.y, 0.0, 1.0);
        gl_PointSize = aSize * uPtScale;
        vAlpha = aAlpha;
      }
    `);
    if (!vs) return false;

    const fs = this._compile(gl, gl.FRAGMENT_SHADER, `
      precision highp float;
      varying float vAlpha;
      uniform vec3 uColor;
      void main() {
        float d = length(gl_PointCoord - 0.5) * 2.0;
        // Very soft falloff — like ink bleeding into paper fibres
        float alpha = vAlpha * exp(-d * d * 2.5);
        alpha *= smoothstep(1.0, 0.5, d);
        gl_FragColor = vec4(uColor, clamp(alpha, 0.0, 1.0));
      }
    `);
    if (!fs) return false;

    const pg = gl.createProgram();
    gl.attachShader(pg, vs);
    gl.attachShader(pg, fs);
    gl.linkProgram(pg);
    if (!gl.getProgramParameter(pg, gl.LINK_STATUS)) {
      console.warn('link error:', gl.getProgramInfoLog(pg));
      return false;
    }
    gl.useProgram(pg);

    this.program = pg;
    this._u = {
      aPos:   gl.getAttribLocation(pg, 'aPos'),
      aSize:  gl.getAttribLocation(pg, 'aSize'),
      aAlpha: gl.getAttribLocation(pg, 'aAlpha'),
      uRes:    gl.getUniformLocation(pg, 'uRes'),
      uPtScale: gl.getUniformLocation(pg, 'uPtScale'),
      uColor:  gl.getUniformLocation(pg, 'uColor'),
    };
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.disable(gl.DEPTH_TEST);
    return true;
  }

  // ─── spawn ──────────────────────────────────────────────

  _spawn(x, y, count) {
    for (let i = 0; i < count; i++) {
      if (this.particles.length >= this.maxParticles) {
        this.particles.shift();
      }
      // Minimal noise — ink sits right under cursor
      const jx = (Math.random() - 0.5) * 0.0015;
      const jy = (Math.random() - 0.5) * 0.0015;
      this.particles.push({
        x: x + jx,
        y: y + jy,
        life: 1.0,
        decay: 0.012 + Math.random() * 0.014,
        size: 4 + Math.random() * 10,
      });
    }
  }

  // ─── update ─────────────────────────────────────────────

  _update(dt) {
    const cappedDt = Math.min(dt, 33);
    const now = performance.now();

    // Spawn every frame when mouse is active — no throttle, no gap
    if (this.mouse.active) {
      // Interpolate along the trail so there are no gaps
      const dx = this.mouse.x - this.mouse.prevX;
      const dy = this.mouse.y - this.mouse.prevY;
      const dist = Math.sqrt(dx*dx + dy*dy);
      const steps = Math.max(1, Math.ceil(dist * 400));
      for (let s = 0; s < steps; s++) {
        const t = steps === 1 ? 1 : s / (steps - 1);
        const ix = this.mouse.prevX + dx * t;
        const iy = this.mouse.prevY + dy * t;
        this._spawn(ix, iy, 1);
      }
    }

    // Update particles — no drift, only size growth (ink bleeding) + fade
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.life -= p.decay * cappedDt * 0.06;
      p.size += 0.012 * cappedDt; // ink slowly bleeds outward
      if (p.life <= 0) this.particles.splice(i, 1);
    }
  }

  // ─── render ─────────────────────────────────────────────

  _render() {
    const gl = this.gl;
    const N = this.particles.length;

    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    if (N === 0) return;

    // Build flat arrays for GPU
    const pos = new Float32Array(N * 2);
    const sz  = new Float32Array(N);
    const al  = new Float32Array(N);
    for (let i = 0; i < N; i++) {
      const p = this.particles[i];
      pos[i*2]   = p.x;
      pos[i*2+1] = p.y;
      sz[i]  = p.size;
      // Alpha follows life curve — stays visible then fades
      al[i]  = p.life * 0.38; // visible ink at birth, fades out
    }

    const a = this._u;

    const posBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
    gl.bufferData(gl.ARRAY_BUFFER, pos, gl.DYNAMIC_DRAW);
    gl.enableVertexAttribArray(a.aPos);
    gl.vertexAttribPointer(a.aPos, 2, gl.FLOAT, false, 0, 0);

    const szBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, szBuf);
    gl.bufferData(gl.ARRAY_BUFFER, sz, gl.DYNAMIC_DRAW);
    gl.enableVertexAttribArray(a.aSize);
    gl.vertexAttribPointer(a.aSize, 1, gl.FLOAT, false, 0, 0);

    const alBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, alBuf);
    gl.bufferData(gl.ARRAY_BUFFER, al, gl.DYNAMIC_DRAW);
    gl.enableVertexAttribArray(a.aAlpha);
    gl.vertexAttribPointer(a.aAlpha, 1, gl.FLOAT, false, 0, 0);

    gl.uniform2f(a.uRes, this.canvas.width, this.canvas.height);
    gl.uniform1f(a.uPtScale, this.canvas.height / 2.2);

    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    // Ink colour — warm grey-black on light, soft grey on dark
    gl.uniform3f(a.uColor, dark ? 0.72 : 0.28, dark ? 0.74 : 0.26, dark ? 0.78 : 0.24);

    gl.drawArrays(gl.POINTS, 0, N);

    gl.deleteBuffer(posBuf);
    gl.deleteBuffer(szBuf);
    gl.deleteBuffer(alBuf);
  }

  // ─── events ─────────────────────────────────────────────

  _bindEvents() {
    window.addEventListener('mousemove', (e) => {
      const x = e.clientX / window.innerWidth;
      const y = 1.0 - e.clientY / window.innerHeight;
      this.mouse.prevX = this.mouse.x;
      this.mouse.prevY = this.mouse.y;
      this.mouse.x = x;
      this.mouse.y = y;
      this.mouse.active = true;
    });
    window.addEventListener('mouseleave', () => {
      this.mouse.active = false;
    });
    // Touch
    window.addEventListener('touchmove', (e) => {
      if (e.touches.length > 0) {
        const x = e.touches[0].clientX / window.innerWidth;
        const y = 1.0 - e.touches[0].clientY / window.innerHeight;
        this.mouse.prevX = this.mouse.x;
        this.mouse.prevY = this.mouse.y;
        this.mouse.x = x;
        this.mouse.y = y;
        this.mouse.active = true;
      }
    }, { passive: true });
    window.addEventListener('touchend', () => { this.mouse.active = false; });
    window.addEventListener('resize', () => this._resize());
  }

  // ─── loop ───────────────────────────────────────────────

  _loop() {
    const now = performance.now();
    const dt = Math.min(now - (this._lastTime || now), 50);
    this._lastTime = now;
    this._update(dt);
    this._render();
    this.rafId = requestAnimationFrame(() => this._loop());
  }

  destroy() {
    cancelAnimationFrame(this.rafId);
    if (this.gl) this.gl.getExtension('WEBGL_lose_context')?.loseContext();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('fluid-canvas');
  if (canvas) new FluidBackground(canvas);
});
