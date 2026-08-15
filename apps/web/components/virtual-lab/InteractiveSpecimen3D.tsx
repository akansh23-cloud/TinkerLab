"use client";

import {PointerEvent as ReactPointerEvent, useEffect, useRef} from "react";

export type LabMode = "thermal" | "dielectric" | "mechanical";

type Props = {
  mode: LabMode;
  intensity: number;
  running: boolean;
  label?: string;
};

const CUBE = new Float32Array([
  // front
  -1,-1, 1,  1,-1, 1,  1, 1, 1,   -1,-1, 1,  1, 1, 1, -1, 1, 1,
  // back
  -1,-1,-1, -1, 1,-1,  1, 1,-1,   -1,-1,-1,  1, 1,-1,  1,-1,-1,
  // top
  -1, 1,-1, -1, 1, 1,  1, 1, 1,   -1, 1,-1,  1, 1, 1,  1, 1,-1,
  // bottom
  -1,-1,-1,  1,-1,-1,  1,-1, 1,   -1,-1,-1,  1,-1, 1, -1,-1, 1,
  // right
   1,-1,-1,  1, 1,-1,  1, 1, 1,    1,-1,-1,  1, 1, 1,  1,-1, 1,
  // left
  -1,-1,-1, -1,-1, 1, -1, 1, 1,   -1,-1,-1, -1, 1, 1, -1, 1,-1,
]);

function compile(gl: WebGLRenderingContext, kind: number, source: string) {
  const shader = gl.createShader(kind);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    console.warn("TinkerLab specimen shader failed", gl.getShaderInfoLog(shader));
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

export function InteractiveSpecimen3D({mode, intensity, running, label="Candidate specimen"}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const state = useRef({rx:-0.35, ry:0.55, dragging:false, x:0, y:0});
  const propsRef = useRef({mode, intensity, running});
  propsRef.current = {mode, intensity, running};

  useEffect(()=>{
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", {antialias:true, alpha:true});
    if (!gl) return;

    const vs = compile(gl, gl.VERTEX_SHADER, `
      attribute vec3 aPosition;
      uniform float uRx;
      uniform float uRy;
      uniform float uAspect;
      varying vec3 vPos;
      varying float vDepth;
      void main(){
        float cx=cos(uRx), sx=sin(uRx), cy=cos(uRy), sy=sin(uRy);
        vec3 p=aPosition;
        p=vec3(p.x, p.y*cx-p.z*sx, p.y*sx+p.z*cx);
        p=vec3(p.x*cy+p.z*sy, p.y, -p.x*sy+p.z*cy);
        p*=vec3(1.18,0.58,0.78);
        p.z-=4.2;
        float focal=2.1;
        gl_Position=vec4((p.x*focal)/uAspect, p.y*focal, p.z+3.0, -p.z);
        vPos=aPosition;
        vDepth=(-p.z-3.0)/2.5;
      }
    `);
    const fs = compile(gl, gl.FRAGMENT_SHADER, `
      precision mediump float;
      uniform float uMode;
      uniform float uIntensity;
      uniform float uTime;
      uniform float uRunning;
      varying vec3 vPos;
      varying float vDepth;
      void main(){
        vec3 base=vec3(0.16,0.43,0.35);
        vec3 thermal=vec3(1.0,0.23,0.035);
        vec3 electric=vec3(0.22,0.48,1.0);
        vec3 mechanical=vec3(0.95,0.62,0.10);
        vec3 active=uMode<0.5?thermal:(uMode<1.5?electric:mechanical);
        float band=0.45+0.35*(vPos.y+1.0)/2.0;
        float pulse=uRunning*(0.06+0.05*sin(uTime*4.0+vPos.x*2.0));
        float amount=clamp(uIntensity*band+pulse,0.0,0.92);
        vec3 col=mix(base,active,amount);
        col*=0.92+0.12*clamp(vDepth,0.0,1.0);
        gl_FragColor=vec4(col,1.0);
      }
    `);
    if(!vs || !fs) return;
    const program=gl.createProgram();
    if(!program) return;
    gl.attachShader(program,vs);gl.attachShader(program,fs);gl.linkProgram(program);
    if(!gl.getProgramParameter(program,gl.LINK_STATUS)) return;
    gl.useProgram(program);

    const buffer=gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,CUBE,gl.STATIC_DRAW);
    const aPosition=gl.getAttribLocation(program,"aPosition");
    gl.enableVertexAttribArray(aPosition);gl.vertexAttribPointer(aPosition,3,gl.FLOAT,false,0,0);
    const uRx=gl.getUniformLocation(program,"uRx");
    const uRy=gl.getUniformLocation(program,"uRy");
    const uAspect=gl.getUniformLocation(program,"uAspect");
    const uMode=gl.getUniformLocation(program,"uMode");
    const uIntensity=gl.getUniformLocation(program,"uIntensity");
    const uTime=gl.getUniformLocation(program,"uTime");
    const uRunning=gl.getUniformLocation(program,"uRunning");
    gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);

    let raf=0;
    const resize=()=>{
      const rect=canvas.getBoundingClientRect();
      const dpr=Math.min(window.devicePixelRatio||1,2);
      const w=Math.max(2,Math.floor(rect.width*dpr));
      const h=Math.max(2,Math.floor(rect.height*dpr));
      if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);}
    };
    const observer=new ResizeObserver(resize);observer.observe(canvas);resize();
    const draw=(t:number)=>{
      resize();
      gl.clearColor(0.035,0.065,0.055,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
      const current=propsRef.current;
      if(!state.current.dragging) state.current.ry+=current.running?0.004:0.0012;
      gl.uniform1f(uRx,state.current.rx);gl.uniform1f(uRy,state.current.ry);
      gl.uniform1f(uAspect,canvas.width/Math.max(canvas.height,1));
      gl.uniform1f(uMode,current.mode==="thermal"?0:current.mode==="dielectric"?1:2);
      gl.uniform1f(uIntensity,Math.max(0,Math.min(1,current.intensity)));
      gl.uniform1f(uTime,t/1000);gl.uniform1f(uRunning,current.running?1:0);
      gl.drawArrays(gl.TRIANGLES,0,CUBE.length/3);
      raf=requestAnimationFrame(draw);
    };
    raf=requestAnimationFrame(draw);
    return ()=>{cancelAnimationFrame(raf);observer.disconnect();gl.deleteBuffer(buffer);gl.deleteProgram(program);gl.deleteShader(vs);gl.deleteShader(fs);};
  },[]);

  const onPointerDown=(e:ReactPointerEvent<HTMLCanvasElement>)=>{
    state.current.dragging=true;state.current.x=e.clientX;state.current.y=e.clientY;
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove=(e:ReactPointerEvent<HTMLCanvasElement>)=>{
    if(!state.current.dragging)return;
    const dx=e.clientX-state.current.x,dy=e.clientY-state.current.y;
    state.current.ry+=dx*0.012;state.current.rx+=dy*0.012;
    state.current.x=e.clientX;state.current.y=e.clientY;
  };
  const stop=()=>{state.current.dragging=false;};

  return <div className="specimen-stage" aria-label={`${label}, interactive 3D visualization`}>
    <canvas ref={canvasRef} className="specimen-canvas" onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={stop} onPointerCancel={stop}/>
    <div className="specimen-caption"><strong>{label}</strong><span>Drag to rotate · visual representation only</span></div>
  </div>;
}
