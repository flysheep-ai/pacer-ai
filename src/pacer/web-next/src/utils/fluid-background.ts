/**
 * Ink Brush Background — mouse as calligraphy brush.
 *
 * Blank canvas. When the mouse moves, it leaves ink-like particles
 * that slowly spread outward and fade, like wet ink bleeding into rice paper.
 * No mouse = empty, quiet, blank.
 */

const VERT = `
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
`

const FRAG = `
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
`

interface Particle {
  x: number
  y: number
  life: number
  decay: number
  size: number
}

interface Uniforms {
  aPos: number
  aSize: number
  aAlpha: number
  uRes: WebGLUniformLocation | null
  uPtScale: WebGLUniformLocation | null
  uColor: WebGLUniformLocation | null
}

export class FluidBackground {
  private readonly canvas: HTMLCanvasElement
  private gl: WebGLRenderingContext | null = null
  private particles: Particle[] = []
  private readonly maxParticles = 400
  private readonly mouse = { x: -1, y: -1, prevX: -1, prevY: -1, active: false }
  private rafId: number | null = null
  private _lastTime = 0
  private _u: Uniforms | null = null

  private _onMouse: ((e: MouseEvent) => void) | null = null
  private _onLeave: (() => void) | null = null
  private _onTouch: ((e: TouchEvent) => void) | null = null
  private _onTouchEnd: (() => void) | null = null
  private _onResize: (() => void) | null = null

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas
    this._init()
  }

  private _init(): void {
    const gl = this.canvas.getContext('webgl', {
      alpha: true,
      antialias: false,
      premultipliedAlpha: false,
      powerPreference: 'high-performance',
    })
    if (!gl) {
      console.warn('WebGL not available')
      return
    }
    this.gl = gl
    this._resize()
    if (!this._buildProgram()) return
    this._bindEvents()
    this._loop()
  }

  private _resize(): void {
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const w = this.canvas.clientWidth * dpr
    const h = this.canvas.clientHeight * dpr
    if (this.canvas.width === w && this.canvas.height === h) return
    this.canvas.width = w
    this.canvas.height = h
    if (this.gl) this.gl.viewport(0, 0, w, h)
  }

  private _compile(
    gl: WebGLRenderingContext,
    type: number,
    src: string,
  ): WebGLShader | null {
    const s = gl.createShader(type)
    if (!s) return null
    gl.shaderSource(s, src)
    gl.compileShader(s)
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.warn('shader error:', gl.getShaderInfoLog(s))
      gl.deleteShader(s)
      return null
    }
    return s
  }

  private _buildProgram(): boolean {
    const gl = this.gl
    if (!gl) return false

    const vs = this._compile(gl, gl.VERTEX_SHADER, VERT)
    if (!vs) return false

    const fs = this._compile(gl, gl.FRAGMENT_SHADER, FRAG)
    if (!fs) return false

    const pg = gl.createProgram()
    if (!pg) return false
    gl.attachShader(pg, vs)
    gl.attachShader(pg, fs)
    gl.linkProgram(pg)
    if (!gl.getProgramParameter(pg, gl.LINK_STATUS)) {
      console.warn('link error:', gl.getProgramInfoLog(pg))
      return false
    }
    gl.useProgram(pg)

    this._u = {
      aPos: gl.getAttribLocation(pg, 'aPos'),
      aSize: gl.getAttribLocation(pg, 'aSize'),
      aAlpha: gl.getAttribLocation(pg, 'aAlpha'),
      uRes: gl.getUniformLocation(pg, 'uRes'),
      uPtScale: gl.getUniformLocation(pg, 'uPtScale'),
      uColor: gl.getUniformLocation(pg, 'uColor'),
    }
    gl.enable(gl.BLEND)
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA)
    gl.disable(gl.DEPTH_TEST)
    return true
  }

  // ─── spawn ──────────────────────────────────────────────

  private _spawn(x: number, y: number, count: number): void {
    for (let i = 0; i < count; i++) {
      if (this.particles.length >= this.maxParticles) {
        this.particles.shift()
      }
      const jx = (Math.random() - 0.5) * 0.002
      const jy = (Math.random() - 0.5) * 0.002
      this.particles.push({
        x: x + jx,
        y: y + jy,
        life: 1.0,
        decay: 0.025 + Math.random() * 0.025,
        size: 1.5 + Math.random() * 3.5,
      })
    }
  }

  // ─── update ─────────────────────────────────────────────

  private _update(dt: number): void {
    const cappedDt = Math.min(dt, 33)

    // Spawn when mouse is active — trail interpolation, lower density
    if (this.mouse.active) {
      const dx = this.mouse.x - this.mouse.prevX
      const dy = this.mouse.y - this.mouse.prevY
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist > 0.0005) {
        const steps = Math.min(Math.ceil(dist * 200), 8)
        for (let s = 0; s < steps; s++) {
          const t = s / Math.max(steps - 1, 1)
          this._spawn(
            this.mouse.prevX + dx * t,
            this.mouse.prevY + dy * t,
            1,
          )
        }
      }
    }

    // Update particles — no drift, only size growth (ink bleeding) + fade
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i]
      p.life -= p.decay * cappedDt * 0.06
      p.size += 0.004 * cappedDt
      if (p.life <= 0) this.particles.splice(i, 1)
    }
  }

  // ─── render ─────────────────────────────────────────────

  private _render(): void {
    const gl = this.gl
    if (!gl) return
    const N = this.particles.length

    gl.clearColor(0, 0, 0, 0)
    gl.clear(gl.COLOR_BUFFER_BIT)

    if (N === 0) return

    // Build flat arrays for GPU
    const pos = new Float32Array(N * 2)
    const sz = new Float32Array(N)
    const al = new Float32Array(N)
    for (let i = 0; i < N; i++) {
      const p = this.particles[i]
      pos[i * 2] = p.x
      pos[i * 2 + 1] = p.y
      sz[i] = p.size
      al[i] = p.life * 0.25
    }

    const a = this._u!
    const canvasW = this.canvas.width
    const canvasH = this.canvas.height

    const posBuf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, posBuf)
    gl.bufferData(gl.ARRAY_BUFFER, pos, gl.DYNAMIC_DRAW)
    gl.enableVertexAttribArray(a.aPos)
    gl.vertexAttribPointer(a.aPos, 2, gl.FLOAT, false, 0, 0)

    const szBuf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, szBuf)
    gl.bufferData(gl.ARRAY_BUFFER, sz, gl.DYNAMIC_DRAW)
    gl.enableVertexAttribArray(a.aSize)
    gl.vertexAttribPointer(a.aSize, 1, gl.FLOAT, false, 0, 0)

    const alBuf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, alBuf)
    gl.bufferData(gl.ARRAY_BUFFER, al, gl.DYNAMIC_DRAW)
    gl.enableVertexAttribArray(a.aAlpha)
    gl.vertexAttribPointer(a.aAlpha, 1, gl.FLOAT, false, 0, 0)

    gl.uniform2f(a.uRes, canvasW, canvasH)
    gl.uniform1f(a.uPtScale, 40.0)

    const dark =
      document.documentElement.getAttribute('data-theme') === 'dark'
    gl.uniform3f(a.uColor, dark ? 0.72 : 0.28, dark ? 0.74 : 0.26, dark ? 0.78 : 0.24)

    gl.drawArrays(gl.POINTS, 0, N)

    gl.deleteBuffer(posBuf)
    gl.deleteBuffer(szBuf)
    gl.deleteBuffer(alBuf)
  }

  // ─── events ─────────────────────────────────────────────

  private _bindEvents(): void {
    this._onMouse = (e: MouseEvent) => {
      this.mouse.prevX = this.mouse.x
      this.mouse.prevY = this.mouse.y
      this.mouse.x = e.clientX / window.innerWidth
      this.mouse.y = 1.0 - e.clientY / window.innerHeight
      this.mouse.active = true
    }
    this._onLeave = () => {
      this.mouse.active = false
    }
    this._onTouch = (e: TouchEvent) => {
      if (e.touches.length > 0) {
        this.mouse.prevX = this.mouse.x
        this.mouse.prevY = this.mouse.y
        this.mouse.x = e.touches[0].clientX / window.innerWidth
        this.mouse.y = 1.0 - e.touches[0].clientY / window.innerHeight
        this.mouse.active = true
      }
    }
    this._onTouchEnd = () => {
      this.mouse.active = false
    }
    this._onResize = () => this._resize()

    window.addEventListener('mousemove', this._onMouse)
    window.addEventListener('mouseleave', this._onLeave)
    window.addEventListener('touchmove', this._onTouch, { passive: true })
    window.addEventListener('touchend', this._onTouchEnd)
    window.addEventListener('resize', this._onResize)
  }

  private _unbindEvents(): void {
    if (this._onMouse) window.removeEventListener('mousemove', this._onMouse)
    if (this._onLeave) window.removeEventListener('mouseleave', this._onLeave)
    if (this._onTouch) window.removeEventListener('touchmove', this._onTouch)
    if (this._onTouchEnd) window.removeEventListener('touchend', this._onTouchEnd)
    if (this._onResize) window.removeEventListener('resize', this._onResize)
  }

  // ─── loop ───────────────────────────────────────────────

  private _loop(): void {
    const now = performance.now()
    const dt = Math.min(now - (this._lastTime || now), 50)
    this._lastTime = now
    this._update(dt)
    this._render()
    this.rafId = requestAnimationFrame(() => this._loop())
  }

  destroy(): void {
    if (this.rafId !== null) cancelAnimationFrame(this.rafId)
    this._unbindEvents()
    if (this.gl) {
      this.gl.getExtension('WEBGL_lose_context')?.loseContext()
      this.gl = null
    }
    this.particles.length = 0
  }
}
