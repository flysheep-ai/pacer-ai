/**
 * Fluid Particle Background — WebGL curl-noise flow field.
 *
 * Design intent: calm, intelligent, "AI is thinking" atmosphere.
 * Not a tech demo. Not sci-fi. Soft, quiet, breathing.
 *
 * Technique:
 *   - Curl noise on a 2D simplicial-like grid drives particle velocity
 *   - Particles are rendered as soft gaussian splats via fragment shader
 *   - Mouse creates a subtle low-pressure zone (gentle attraction, not chase)
 *   - All colours are low-saturation greys / cool blues
 */
class FluidBackground {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = null;
    this.particleCount = 280;
    this.mouse = { x: -9999, y: -9999, targetX: 0.5, targetY: 0.5 };
    this.time = 0;
    this.rafId = null;
    this.isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    this._init();
  }

  _init() {
    const gl = this.canvas.getContext('webgl', {
      alpha: true,
      antialias: false,
      powerPreference: 'high-performance',
    });
    if (!gl) return;
    this.gl = gl;

    this._resize();
    this._createProgram();
    this._createParticles();
    this._bindEvents();
    this._loop();
  }

  _resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2); // cap at 2x for perf
    this.canvas.width = this.canvas.clientWidth * dpr;
    this.canvas.height = this.canvas.clientHeight * dpr;
    if (this.gl) {
      this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    }
  }

  // ─── shaders ────────────────────────────────────────────

  _createProgram() {
    const gl = this.gl;

    // ── vertex shader ──
    // Renders each particle as a camera-facing point sprite.
    const vs = gl.createShader(gl.VERTEX_SHADER);
    gl.shaderSource(vs, /* glsl */`
      precision highp float;
      attribute vec2 aPos;
      attribute float aSize;
      attribute float aAlpha;
      uniform vec2 uRes;
      uniform float uPointScale;
      varying float vAlpha;
      varying float vSize;
      void main() {
        vec2 ndc = aPos * 2.0 - 1.0;
        ndc.y *= -1.0; // flip Y
        gl_Position = vec4(ndc, 0.0, 1.0);
        gl_PointSize = aSize * uPointScale;
        vAlpha = aAlpha;
        vSize = aSize;
      }
    `);
    gl.compileShader(vs);

    // ── fragment shader ──
    // Soft gaussian-like splat. No hard edges.
    const fs = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(fs, /* glsl */`
      precision highp float;
      varying float vAlpha;
      varying float vSize;
      uniform vec3 uColor;
      void main() {
        float d = length(gl_PointCoord - 0.5) * 2.0;
        // Gaussian falloff — soft, no visible edge
        float alpha = vAlpha * exp(-d * d * 3.5);
        alpha *= smoothstep(1.0, 0.7, d); // smooth cut at edge
        alpha = clamp(alpha, 0.0, 1.0);
        gl_FragColor = vec4(uColor, alpha);
      }
    `);
    gl.compileShader(fs);

    // ── program ──
    const program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    gl.useProgram(program);

    this.program = program;
    this.uRes = gl.getUniformLocation(program, 'uRes');
    this.uPointScale = gl.getUniformLocation(program, 'uPointScale');
    this.uColor = gl.getUniformLocation(program, 'uColor');

    // Blending — additive but very subtle (low alpha per particle)
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.disable(gl.DEPTH_TEST);
  }

  // ─── particles ──────────────────────────────────────────

  _createParticles() {
    const gl = this.gl;
    const N = this.particleCount;

    // Initialise positions clustered in the upper-centre area
    // so the background has breathing room at edges.
    const positions = new Float32Array(N * 2);
    const velocities = new Float32Array(N * 2); // stored as [0,1] space
    const sizes = new Float32Array(N);
    const alphas = new Float32Array(N);

    for (let i = 0; i < N; i++) {
      // Bias toward upper-centre (like subtle light source)
      const cx = 0.5 + (Math.random() - 0.5) * 0.6;
      const cy = 0.35 + (Math.random() - 0.5) * 0.5;
      positions[i * 2] = Math.max(0.02, Math.min(0.98, cx));
      positions[i * 2 + 1] = Math.max(0.02, Math.min(0.98, cy));
      velocities[i * 2] = 0;
      velocities[i * 2 + 1] = 0;
      sizes[i] = 10 + Math.random() * 50;
      alphas[i] = 0.12 + Math.random() * 0.18;
    }

    this.positions = positions;
    this.velocities = velocities;
    this.sizes = sizes;
    this.alphas = alphas;

    // Upload static attributes
    const posBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
    gl.bufferData(gl.ARRAY_BUFFER, positions, gl.DYNAMIC_DRAW);
    const aPos = gl.getAttribLocation(this.program, 'aPos');
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    const sizeBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, sizeBuf);
    gl.bufferData(gl.ARRAY_BUFFER, sizes, gl.STATIC_DRAW);
    const aSize = gl.getAttribLocation(this.program, 'aSize');
    gl.enableVertexAttribArray(aSize);
    gl.vertexAttribPointer(aSize, 1, gl.FLOAT, false, 0, 0);

    const alphaBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, alphaBuf);
    gl.bufferData(gl.ARRAY_BUFFER, alphas, gl.STATIC_DRAW);
    const aAlpha = gl.getAttribLocation(this.program, 'aAlpha');
    gl.enableVertexAttribArray(aAlpha);
    gl.vertexAttribPointer(aAlpha, 1, gl.FLOAT, false, 0, 0);
  }

  // ─── curl noise (simplicial-like) ───────────────────────

  /** Hash function for noise. Returns pseudo-random 2D vector. */
  _hash(p) {
    // From https://www.shadertoy.com/view/4djSRW (Markus Kummer)
    const h = [p[0] * 127.1 + p[1] * 311.7, p[0] * 269.5 + p[1] * 183.3];
    const s = Math.sin(h[0]) * 43758.5453 + Math.sin(h[1]) * 43758.5453;
    const r = (s - Math.floor(s)) * 2.0 - 1.0;
    return [
      Math.sin(r * 6.283) * 0.5 + 0.5,
      Math.cos(r * 6.283) * 0.5 + 0.5,
    ];
  }

  /** Smooth noise at point p. */
  _noise(p) {
    const i = [Math.floor(p[0]), Math.floor(p[1])];
    const f = [p[0] - i[0], p[1] - i[1]];
    // Smoothstep
    const u = [f[0] * f[0] * (3.0 - 2.0 * f[0]), f[1] * f[1] * (3.0 - 2.0 * f[1])];
    const n00 = this._hash([i[0], i[1]]);
    const n10 = this._hash([i[0] + 1, i[1]]);
    const n01 = this._hash([i[0], i[1] + 1]);
    const n11 = this._hash([i[0] + 1, i[1] + 1]);
    const nx0 = n00[0] * (1 - u[0]) + n10[0] * u[0];
    const nx1 = n01[0] * (1 - u[0]) + n11[0] * u[0];
    return nx0 * (1 - u[1]) + nx1 * u[1];
  }

  /** Curl of a 2D noise field. Returns divergence-free velocity. */
  _curl(x, y, t) {
    const eps = 0.01;
    const n1 = this._noise([x + eps, y + t * 0.02]);
    const n2 = this._noise([x - eps, y + t * 0.02]);
    const n3 = this._noise([x + t * 0.02, y + eps]);
    const n4 = this._noise([x + t * 0.02, y - eps]);
    // curl = (dFy/dx - dFx/dy) → in 2D: velocity = (dN/dy, -dN/dx)
    return [
      (n3 - n4) / (2 * eps),
      -(n1 - n2) / (2 * eps),
    ];
  }

  // ─── update ─────────────────────────────────────────────

  _update(dt) {
    const N = this.particleCount;
    const pos = this.positions;
    const vel = this.velocities;
    const t = this.time;

    // Smooth mouse target
    const mx = this.mouse.targetX;
    const my = this.mouse.targetY;

    for (let i = 0; i < N; i++) {
      const px = pos[i * 2];
      const py = pos[i * 2 + 1];

      // Curl noise field velocity — base flow
      const [cvx, cvy] = this._curl(px * 3.0, py * 3.0, t * 0.15);

      // Subtle mouse influence — gentle low-pressure zone (not chase)
      const dx = px - mx;
      const dy = py - my;
      const dist = Math.sqrt(dx * dx + dy * dy) + 0.001;
      const mouseForce = 0.00006 / (dist * dist + 0.01); // inverse-square, capped
      const mxInfluence = dx / dist * mouseForce;
      const myInfluence = dy / dist * mouseForce;

      // Combine forces. Curl noise drives primary motion; mouse adds subtle disturbance.
      const speed = 0.00025 * dt;
      vel[i * 2] = cvx * speed + mxInfluence * dt * 0.03;
      vel[i * 2 + 1] = cvy * speed + myInfluence * dt * 0.03;

      // Integrate
      pos[i * 2] += vel[i * 2];
      pos[i * 2 + 1] += vel[i * 2 + 1];

      // Wrap-around with soft fade — keeps particles in a gentle band
      if (pos[i * 2] < -0.05) pos[i * 2] = 1.05;
      if (pos[i * 2] > 1.05) pos[i * 2] = -0.05;
      if (pos[i * 2 + 1] < -0.05) pos[i * 2 + 1] = 1.05;
      if (pos[i * 2 + 1] > 1.05) pos[i * 2 + 1] = -0.05;
    }
  }

  // ─── render ─────────────────────────────────────────────

  _render() {
    const gl = this.gl;
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    gl.useProgram(this.program);

    // Update position buffer
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.getAttribLocation(this.program, 'aPos') !== -1
      ? gl.createBuffer() : gl.createBuffer());
    // Actually, just rebind the existing buffer
    const aPosLoc = gl.getAttribLocation(this.program, 'aPos');
    // Re-upload positions
    const allBufs = gl.getParameter(gl.ARRAY_BUFFER_BINDING);
    // Create a fresh upload each frame (pragmatic for dynamic data)
    const dynBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, dynBuf);
    gl.bufferData(gl.ARRAY_BUFFER, this.positions, gl.DYNAMIC_DRAW);
    gl.enableVertexAttribArray(aPosLoc);
    gl.vertexAttribPointer(aPosLoc, 2, gl.FLOAT, false, 0, 0);
    // Re-bind size & alpha (their attrib locations may have been lost after re-bind)
    const aSizeLoc = gl.getAttribLocation(this.program, 'aSize');
    const sizeBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, sizeBuf);
    gl.bufferData(gl.ARRAY_BUFFER, this.sizes, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(aSizeLoc);
    gl.vertexAttribPointer(aSizeLoc, 1, gl.FLOAT, false, 0, 0);

    const aAlphaLoc = gl.getAttribLocation(this.program, 'aAlpha');
    const alphaBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, alphaBuf);
    gl.bufferData(gl.ARRAY_BUFFER, this.alphas, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(aAlphaLoc);
    gl.vertexAttribPointer(aAlphaLoc, 1, gl.FLOAT, false, 0, 0);

    gl.uniform2f(this.uRes, this.canvas.width, this.canvas.height);
    gl.uniform1f(this.uPointScale, this.canvas.height / 2.0);

    // Colour — muted cool-grey, shifts subtly with dark/light mode
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (isDark) {
      gl.uniform3f(this.uColor, 0.58, 0.65, 0.78); // soft cool blue-grey
    } else {
      gl.uniform3f(this.uColor, 0.45, 0.50, 0.60); // warm grey-blue
    }

    gl.drawArrays(gl.POINTS, 0, this.particleCount);

    // Clean up temp buffers (WebGL will GC unreferenced buffers)
    gl.deleteBuffer(dynBuf);
    gl.deleteBuffer(sizeBuf);
    gl.deleteBuffer(alphaBuf);
  }

  // ─── events ─────────────────────────────────────────────

  _bindEvents() {
    window.addEventListener('resize', () => this._resize());
    this.canvas.addEventListener('mousemove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      this.mouse.targetX = (e.clientX - rect.left) / rect.width;
      this.mouse.targetY = 1.0 - (e.clientY - rect.top) / rect.height;
    });
    this.canvas.addEventListener('mouseleave', () => {
      this.mouse.targetX = 0.5;
      this.mouse.targetY = 0.5;
    });
    // Touch support
    this.canvas.addEventListener('touchmove', (e) => {
      if (e.touches.length > 0) {
        const rect = this.canvas.getBoundingClientRect();
        this.mouse.targetX = (e.touches[0].clientX - rect.left) / rect.width;
        this.mouse.targetY = 1.0 - (e.touches[0].clientY - rect.top) / rect.height;
      }
    }, { passive: true });
    // Theme changes
    new MutationObserver(() => {
      this.isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  }

  // ─── loop ───────────────────────────────────────────────

  _loop() {
    const now = performance.now();
    const dt = Math.min(now - (this._lastTime || now), 50); // cap at 50ms
    this._lastTime = now;
    this.time += dt * 0.001;

    this._update(dt);
    this._render();

    this.rafId = requestAnimationFrame(() => this._loop());
  }

  destroy() {
    if (this.rafId) cancelAnimationFrame(this.rafId);
    if (this.gl) {
      this.gl.getExtension('WEBGL_lose_context')?.loseContext();
    }
  }
}

// ─── auto-init when DOM ready ─────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('fluid-canvas');
  if (canvas) {
    new FluidBackground(canvas);
  }
});
