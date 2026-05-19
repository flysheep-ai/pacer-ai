/**
 * Fluid Particle Background — WebGL curl-noise flow field.
 *
 * Calm, quiet, "AI is thinking" atmosphere.
 * GPU-rendered point sprites driven by a 2D curl-noise velocity field.
 * Mouse creates a subtle low-pressure disturbance (not chase behaviour).
 */
class FluidBackground {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = null;
    this.particleCount = 240;
    this.mouse = { tx: 0.5, ty: 0.5 };
    this.time = 0;
    this._lastTime = 0;
    this.rafId = null;
    this._attribs = {};   // cached attribute locations
    this._bufs = {};       // cached buffer objects
    this._init();
  }

  _init() {
    const gl = this.canvas.getContext('webgl', {
      alpha: true,
      antialias: false,
      premultipliedAlpha: false,
      powerPreference: 'high-performance',
    });
    if (!gl) { console.warn('WebGL not available'); return; }
    this.gl = gl;

    this._resize();
    if (!this._buildProgram()) { console.warn('shader compile failed'); return; }
    this._initParticles();
    this._bindEvents();
    this._loop();
  }

  // ─── resize ─────────────────────────────────────────────

  _resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = this.canvas.clientWidth * dpr;
    const h = this.canvas.clientHeight * dpr;
    if (this.canvas.width === w && this.canvas.height === h) return;
    this.canvas.width = w;
    this.canvas.height = h;
    if (this.gl) this.gl.viewport(0, 0, w, h);
  }

  // ─── shader program ─────────────────────────────────────

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
        gl_Position = vec4(ndc.x, -ndc.y, 0.0, 1.0);
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
        float alpha = vAlpha * exp(-d * d * 4.0);
        alpha *= smoothstep(1.0, 0.6, d);
        gl_FragColor = vec4(uColor, clamp(alpha, 0.0, 1.0));
      }
    `);
    if (!fs) return false;

    const pg = gl.createProgram();
    gl.attachShader(pg, vs);
    gl.attachShader(pg, fs);
    gl.linkProgram(pg);
    if (!gl.getProgramParameter(pg, gl.LINK_STATUS)) {
      console.warn('program link error:', gl.getProgramInfoLog(pg));
      return false;
    }
    gl.useProgram(pg);

    this.program = pg;
    this._attribs.aPos   = gl.getAttribLocation(pg, 'aPos');
    this._attribs.aSize  = gl.getAttribLocation(pg, 'aSize');
    this._attribs.aAlpha = gl.getAttribLocation(pg, 'aAlpha');
    this._attribs.uRes    = gl.getUniformLocation(pg, 'uRes');
    this._attribs.uPtScale = gl.getUniformLocation(pg, 'uPtScale');
    this._attribs.uColor  = gl.getUniformLocation(pg, 'uColor');

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.disable(gl.DEPTH_TEST);
    return true;
  }

  // ─── particles ──────────────────────────────────────────

  _initParticles() {
    const gl = this.gl;
    const N = this.particleCount;
    const pos = new Float32Array(N * 2);
    const vel = new Float32Array(N * 2);
    const sz  = new Float32Array(N);
    const al  = new Float32Array(N);

    for (let i = 0; i < N; i++) {
      pos[i*2]   = 0.5 + (Math.random() - 0.5) * 0.7;
      pos[i*2+1] = 0.35 + (Math.random() - 0.5) * 0.55;
      vel[i*2] = vel[i*2+1] = 0;
      sz[i] = 8 + Math.random() * 60;
      al[i] = 0.10 + Math.random() * 0.16;
    }

    this.positions = pos;
    this.velocities = vel;
    this.sizes = sz;
    this.alphas = al;

    // Create persistent buffers
    this._bufs.pos = this._makeBuf(gl.ARRAY_BUFFER, pos, gl.DYNAMIC_DRAW);
    this._bufs.sz  = this._makeBuf(gl.ARRAY_BUFFER, sz, gl.STATIC_DRAW);
    this._bufs.al  = this._makeBuf(gl.ARRAY_BUFFER, al, gl.STATIC_DRAW);
  }

  _makeBuf(target, data, usage) {
    const gl = this.gl;
    const b = gl.createBuffer();
    gl.bindBuffer(target, b);
    gl.bufferData(target, data, usage);
    return b;
  }

  // ─── curl noise ─────────────────────────────────────────

  _hash2(x, y) {
    // PCG-like hash returning [0,1)
    let h = (x * 374761393 + y * 668265263) >>> 0;
    h = ((h ^ (h >> 13)) * 1274126177) >>> 0;
    return (h ^ (h >> 16)) / 4294967296;
  }

  _noise(x, y) {
    const ix = Math.floor(x), iy = Math.floor(y);
    const fx = x - ix, fy = y - iy;
    const ux = fx * fx * (3 - 2 * fx);
    const uy = fy * fy * (3 - 2 * fy);
    const a = this._hash2(ix, iy);
    const b = this._hash2(ix + 1, iy);
    const c = this._hash2(ix, iy + 1);
    const d = this._hash2(ix + 1, iy + 1);
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy;
  }

  _curl(x, y, t) {
    const e = 0.008;
    const n1 = this._noise(x + e, y + t);
    const n2 = this._noise(x - e, y + t);
    const n3 = this._noise(x + t, y + e);
    const n4 = this._noise(x + t, y - e);
    // 2D curl: (d/dy, -d/dx)
    return [(n3 - n4) / (2*e), -(n1 - n2) / (2*e)];
  }

  // ─── update ─────────────────────────────────────────────

  _update(dt) {
    const N = this.particleCount;
    const p = this.positions;
    const v = this.velocities;
    const t = this.time;
    const mx = this.mouse.tx, my = this.mouse.ty;
    const cappedDt = Math.min(dt, 33);
    const curlSpeed = 0.00015 * cappedDt;
    const mouseFactor = 0.003 * cappedDt; // much stronger mouse response

    for (let i = 0; i < N; i++) {
      const px = p[i*2], py = p[i*2+1];

      // Curl noise base flow (slower, so mouse interaction is more visible)
      const [cvx, cvy] = this._curl(px * 2.8, py * 2.8, t * 0.12);

      // Mouse — gentle swirl toward cursor
      const dx = px - mx, dy = py - my;
      const dist = Math.sqrt(dx*dx + dy*dy) + 0.001;

      // Influence radius: visible up to ~30% of screen
      const w = 1.0 / (1.0 + dist * dist * 50.0);

      // Clockwise swirl around mouse
      const sx = -dy / dist * w;
      const sy =  dx / dist * w;

      v[i*2]   = cvx * curlSpeed + sx * mouseFactor;
      v[i*2+1] = cvy * curlSpeed + sy * mouseFactor;

      // Integrate
      p[i*2]   += v[i*2];
      p[i*2+1] += v[i*2+1];

      // Wrap
      if (p[i*2] < -0.08) p[i*2] = 1.08;
      if (p[i*2] > 1.08) p[i*2] = -0.08;
      if (p[i*2+1] < -0.08) p[i*2+1] = 1.08;
      if (p[i*2+1] > 1.08) p[i*2+1] = -0.08;
    }
  }

  // ─── render ─────────────────────────────────────────────

  _render() {
    const gl = this.gl;
    const a = this._attribs;

    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    // Upload dynamic position buffer (reuse)
    gl.bindBuffer(gl.ARRAY_BUFFER, this._bufs.pos);
    gl.bufferData(gl.ARRAY_BUFFER, this.positions, gl.DYNAMIC_DRAW);
    gl.enableVertexAttribArray(a.aPos);
    gl.vertexAttribPointer(a.aPos, 2, gl.FLOAT, false, 0, 0);

    // Bind static size buffer
    gl.bindBuffer(gl.ARRAY_BUFFER, this._bufs.sz);
    gl.enableVertexAttribArray(a.aSize);
    gl.vertexAttribPointer(a.aSize, 1, gl.FLOAT, false, 0, 0);

    // Bind static alpha buffer
    gl.bindBuffer(gl.ARRAY_BUFFER, this._bufs.al);
    gl.enableVertexAttribArray(a.aAlpha);
    gl.vertexAttribPointer(a.aAlpha, 1, gl.FLOAT, false, 0, 0);

    gl.uniform2f(a.uRes, this.canvas.width, this.canvas.height);
    gl.uniform1f(a.uPtScale, this.canvas.height / 2.2);

    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    gl.uniform3f(a.uColor, dark ? 0.60 : 0.44, dark ? 0.66 : 0.50, dark ? 0.76 : 0.58);

    gl.drawArrays(gl.POINTS, 0, this.particleCount);
  }

  // ─── events ─────────────────────────────────────────────

  _bindEvents() {
    // Mouse tracking on window (not canvas — keeps form clickable)
    window.addEventListener('mousemove', (e) => {
      this.mouse.tx = e.clientX / window.innerWidth;
      this.mouse.ty = 1.0 - e.clientY / window.innerHeight;
    });
    window.addEventListener('resize', () => this._resize());
  }

  // ─── loop ───────────────────────────────────────────────

  _loop() {
    const now = performance.now();
    const dt = Math.min(now - this._lastTime, 50);
    this._lastTime = now;
    this.time += dt * 0.001;
    this._update(dt);
    this._render();
    this.rafId = requestAnimationFrame(() => this._loop());
  }

  destroy() {
    cancelAnimationFrame(this.rafId);
    if (this.gl) this.gl.getExtension('WEBGL_lose_context')?.loseContext();
  }
}

// Auto-init
document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('fluid-canvas');
  if (canvas) new FluidBackground(canvas);
});
