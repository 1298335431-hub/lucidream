import { useEffect, useRef } from "react";
import { ArrowRight } from "lucide-react";
import { gsap } from "gsap";
import "./liquid-login-button.css";

type LiquidLoginButtonProps = {
  onClick?: () => void;
  attentionKey?: number;
};

export function LiquidLoginButton({ onClick, attentionKey = 0 }: LiquidLoginButtonProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    const button = buttonRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !button || !canvas) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const intro = reducedMotion
      ? undefined
      : gsap.fromTo(
          wrap,
          { autoAlpha: 0, y: -7, scale: 0.96 },
          { autoAlpha: 1, y: 0, scale: 1, duration: 0.65, ease: "power3.out" },
        );
    if (reducedMotion) gsap.set(wrap, { autoAlpha: 1 });

    const gl = canvas.getContext("webgl", { alpha: false, antialias: false });
    if (!gl) {
      button.classList.add("is-static");
      return () => intro?.kill();
    }

    const vertexSource = "attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}";
    const fragmentSource = [
      "precision mediump float;",
      "uniform vec2 u_res; uniform float u_time; uniform float u_level; uniform float u_tilt; uniform float u_slosh;",
      "float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453123);}",
      "float noise(vec2 p){vec2 i=floor(p),f=fract(p);vec2 u=f*f*(3.0-2.0*f);return mix(mix(hash(i),hash(i+vec2(1.,0.)),u.x),mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),u.x),u.y);}",
      "float fbm(vec2 p){float v=0.0;float a=0.5;for(int i=0;i<3;i++){v+=a*noise(p);p=p*2.04+vec2(11.3,7.1);a*=0.5;}return v;}",
      "void main(){",
      "vec2 uv=gl_FragCoord.xy/u_res;float ar=u_res.x/u_res.y;float x=uv.x*ar;float amp=0.010+u_slosh*0.035;",
      "float surf=u_level+u_tilt*(uv.x-0.5)*0.28+amp*sin(x*5.1+u_time*3.8)+amp*0.55*sin(x*9.7-u_time*5.2+1.7);",
      "float d=surf-uv.y;vec3 col=mix(vec3(0.91,0.92,0.97),vec3(0.965,0.97,1.0),uv.y);",
      "float inside=smoothstep(0.0,0.018,d);float depth=clamp(d/max(u_level,0.001),0.0,1.0);",
      "vec3 liq=mix(vec3(0.66,0.70,0.88),vec3(0.86,0.89,0.97),depth);liq*=0.91+0.16*fbm(vec2(x*3.8,(uv.y+u_time*0.1)*3.8));",
      "col=mix(col,liq,inside);col+=vec3(0.91,0.93,1.0)*exp(-abs(d)*70.0)*0.48;",
      "vec2 e=uv*(1.0-uv);col*=0.9+0.1*pow(e.x*e.y*16.0,0.22);gl_FragColor=vec4(col,1.0);}",
    ].join("\n");

    const compile = (type: number, source: string) => {
      const shader = gl.createShader(type);
      if (!shader) return null;
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        gl.deleteShader(shader);
        return null;
      }
      return shader;
    };

    const vertexShader = compile(gl.VERTEX_SHADER, vertexSource);
    const fragmentShader = compile(gl.FRAGMENT_SHADER, fragmentSource);
    const program = gl.createProgram();
    if (!vertexShader || !fragmentShader || !program) {
      button.classList.add("is-static");
      return () => intro?.kill();
    }

    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      button.classList.add("is-static");
      return () => intro?.kill();
    }
    gl.useProgram(program);

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, "p");
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

    const resolution = gl.getUniformLocation(program, "u_res");
    const time = gl.getUniformLocation(program, "u_time");
    const levelUniform = gl.getUniformLocation(program, "u_level");
    const tiltUniform = gl.getUniformLocation(program, "u_tilt");
    const sloshUniform = gl.getUniformLocation(program, "u_slosh");

    let frameId = 0;
    let lastFrame = 0;
    let lastTime = performance.now();
    let slosh = 0.28;
    let tilt = 0;
    let tiltTarget = 0;
    let gulp = 0;
    let level = 0.55;
    let lastX: number | null = null;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const width = Math.max(1, Math.round(canvas.clientWidth * dpr));
      const height = Math.max(1, Math.round(canvas.clientHeight * dpr));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
        gl.viewport(0, 0, width, height);
      }
    };

    const render = (now: number) => {
      frameId = window.requestAnimationFrame(render);
      if (document.hidden || now - lastFrame < 1000 / 30) return;
      const delta = Math.min(0.05, (now - lastTime) / 1000);
      lastFrame = now;
      lastTime = now;
      slosh *= Math.exp(-1.7 * delta);
      gulp *= Math.exp(-1.25 * delta);
      tilt += (tiltTarget - tilt) * Math.min(1, delta * 5);
      level += (0.55 - 0.28 * gulp - level) * Math.min(1, delta * 5.5);
      resize();
      gl.uniform2f(resolution, canvas.width, canvas.height);
      gl.uniform1f(time, reducedMotion ? 2 : now / 1000);
      gl.uniform1f(levelUniform, level);
      gl.uniform1f(tiltUniform, tilt);
      gl.uniform1f(sloshUniform, reducedMotion ? 0.12 : slosh);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (reducedMotion) window.cancelAnimationFrame(frameId);
    };

    const handleMove = (event: PointerEvent) => {
      const rect = button.getBoundingClientRect();
      const x = (event.clientX - rect.left) / Math.max(1, rect.width);
      if (lastX !== null) slosh = Math.min(1.25, slosh + Math.abs(x - lastX) * 2.4);
      lastX = x;
      tiltTarget = Math.max(-1, Math.min(1, (x - 0.5) * 2));
    };
    const handleLeave = () => {
      lastX = null;
      tiltTarget = 0;
    };
    const handlePress = () => {
      gulp = 1;
      slosh = Math.min(1.25, slosh + 0.65);
    };

    button.addEventListener("pointermove", handleMove);
    button.addEventListener("pointerleave", handleLeave);
    button.addEventListener("click", handlePress);
    frameId = window.requestAnimationFrame(render);

    return () => {
      intro?.kill();
      window.cancelAnimationFrame(frameId);
      button.removeEventListener("pointermove", handleMove);
      button.removeEventListener("pointerleave", handleLeave);
      button.removeEventListener("click", handlePress);
      gl.deleteBuffer(buffer);
      gl.deleteProgram(program);
      gl.deleteShader(vertexShader);
      gl.deleteShader(fragmentShader);
    };
  }, []);

  useEffect(() => {
    if (!attentionKey || !wrapRef.current) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timeline = gsap.timeline();
    if (reducedMotion) {
      timeline
        .to(wrapRef.current, { opacity: .62, duration: .12 })
        .to(wrapRef.current, { opacity: 1, duration: .18 });
    } else {
      timeline
        .to(wrapRef.current, { x: -5, rotation: -.8, duration: .07, ease: "power1.inOut" })
        .to(wrapRef.current, { x: 5, rotation: .8, duration: .08, ease: "power1.inOut", repeat: 3, yoyo: true })
        .to(wrapRef.current, { x: 0, rotation: 0, duration: .12, ease: "power2.out" });
    }
    return () => {
      timeline.kill();
      gsap.set(wrapRef.current, { x: 0, rotation: 0 });
    };
  }, [attentionKey]);

  return (
    <div className="liquid-login-frame" ref={wrapRef}>
      <button className="liquid-login-button" ref={buttonRef} type="button" onClick={onClick} aria-label="Login">
        <canvas ref={canvasRef} aria-hidden="true" />
        <span>Login</span>
        <ArrowRight aria-hidden="true" size={14} strokeWidth={1.45} />
      </button>
    </div>
  );
}
