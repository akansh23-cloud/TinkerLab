"use client";

import {LabMode} from "./InteractiveSpecimen3D";

type Props={mode:LabMode;progress:number;running:boolean;temperature:number;voltage:number;load:number;atmosphere:string};

export function IndustrialRig({mode,progress,running,temperature,voltage,load,atmosphere}:Props){
  const p=Math.max(0,Math.min(1,progress));
  if(mode==="thermal") return <div className={`industrial-rig ${running?"rig-running":""}`}>
    <svg viewBox="0 0 820 360" role="img" aria-label="Industrial thermal furnace visualization">
      <defs>
        <linearGradient id="furnaceShell" x1="0" x2="1"><stop offset="0" stopColor="#182536"/><stop offset="1" stopColor="#263a52"/></linearGradient>
        <radialGradient id="heatCore"><stop offset="0" stopColor={`rgba(255,190,62,${.18+.72*p})`}/><stop offset="1" stopColor={`rgba(255,71,25,${.05+.36*p})`}/></radialGradient>
      </defs>
      <rect x="42" y="48" width="560" height="250" rx="26" fill="url(#furnaceShell)"/>
      <rect x="116" y="82" width="390" height="176" rx="18" fill="#07121e" stroke="#3a526e" strokeWidth="4"/>
      <rect x="135" y="99" width="352" height="142" rx="14" fill="url(#heatCore)"/>
      {[0,1,2,3,4].map(i=><path key={i} d={`M ${154+i*68} 112 q 20 18 0 36 q -20 18 0 36 q 20 18 0 36`} fill="none" stroke={running?"#ff7b37":"#79665c"} strokeWidth="8" strokeLinecap="round" className="heater-coil"/>)}
      <rect x="260" y="176" width="110" height="28" rx="5" fill={running?"#e16b35":"#28546a"} stroke="#b7c9e0" strokeOpacity=".45"/>
      <line x1="315" y1="204" x2="315" y2="232" stroke="#526983" strokeWidth="5"/><rect x="245" y="231" width="140" height="12" rx="6" fill="#3a5067"/>
      <rect x="630" y="75" width="145" height="190" rx="18" fill="#0d1b2b" stroke="#2a405b"/>
      <text x="651" y="110" fontSize="14" fontWeight="700" fill="#7186a4">FURNACE CTRL</text>
      <text x="651" y="151" fontSize="31" fontWeight="800" fill="#dce8f8">{Math.round(25+(temperature-25)*p)} K</text>
      <text x="651" y="181" fontSize="13" fill="#6e829e">Target {temperature} K</text>
      <text x="651" y="208" fontSize="13" fill="#6e829e">Atmosphere</text><text x="651" y="230" fontSize="14" fontWeight="700" fill="#3c94ff">{atmosphere}</text>
      <path d="M 80 318 H 742" stroke="#31465f" strokeWidth="3"/><circle cx={80+662*p} cy="318" r="8" fill="#3c94ff"/>
    </svg>
    <div className="rig-label"><strong>Industrial thermal exposure cell</strong><span>Heater animation is a process visualization. It does not create a physical measurement.</span></div>
  </div>;

  if(mode==="dielectric") return <div className={`industrial-rig ${running?"rig-running":""}`}>
    <svg viewBox="0 0 820 360" role="img" aria-label="High voltage dielectric breakdown visualization">
      <rect x="54" y="48" width="520" height="250" rx="26" fill="#142334"/>
      <rect x="126" y="82" width="372" height="176" rx="18" fill="#07121e" stroke="#324a66" strokeWidth="3"/>
      <rect x="265" y="151" width="94" height="58" rx="5" fill="#24536e" stroke="#6f8ca8"/>
      <rect x="166" y="168" width="99" height="23" rx="6" fill="#55728e"/><rect x="359" y="168" width="99" height="23" rx="6" fill="#55728e"/>
      <line x1="166" y1="180" x2="94" y2="180" stroke="#6aa7ff" strokeWidth="6"/><line x1="458" y1="180" x2="530" y2="180" stroke="#6aa7ff" strokeWidth="6"/>
      {running&&p>.25&&<path d="M 264 178 L 286 163 L 304 193 L 326 157 L 346 186 L 359 178" fill="none" stroke="#91bdff" strokeWidth={3+4*p} className="electric-arc"/>}
      <rect x="610" y="76" width="160" height="187" rx="18" fill="#0d1b2b" stroke="#2a405b"/>
      <text x="632" y="111" fontSize="14" fontWeight="700" fill="#7186a4">HV SOURCE</text>
      <text x="632" y="153" fontSize="30" fontWeight="800" fill="#dce8f8">{(voltage*p).toFixed(1)} kV</text>
      <text x="632" y="182" fontSize="13" fill="#6e829e">Target {voltage} kV</text>
      <text x="632" y="216" fontSize="13" fill="#6e829e">Ramp</text><text x="632" y="238" fontSize="14" fontWeight="700" fill="#315f9f">controlled</text>
      <path d="M 80 318 H 742" stroke="#31465f" strokeWidth="3"/><circle cx={80+662*p} cy="318" r="8" fill="#315f9f"/>
    </svg>
    <div className="rig-label"><strong>High-voltage test cell</strong><span>The arc is illustrative. Authoritative breakdown conclusions must come from evidence or a validated solver.</span></div>
  </div>;

  return <div className={`industrial-rig ${running?"rig-running":""}`}>
    <svg viewBox="0 0 820 360" role="img" aria-label="Universal testing machine visualization">
      <rect x="62" y="35" width="500" height="277" rx="22" fill="#142233"/>
      <rect x="112" y="62" width="34" height="222" rx="8" fill="#405873"/><rect x="478" y="62" width="34" height="222" rx="8" fill="#405873"/>
      <rect x="137" y="78" width="350" height="34" rx="9" fill="#57718d"/><rect x="137" y="245" width="350" height="34" rx="9" fill="#57718d"/>
      <rect x="277" y="112" width="70" height="46" rx="7" fill="#314c65"/><rect x="277" y="200" width="70" height="45" rx="7" fill="#314c65"/>
      <rect x={304-3*p} y={157-10*p} width={16+6*p} height={44+20*p} rx="4" fill={p>.75?"#e2a33e":"#2f6b7e"} stroke="#b7c9df"/>
      <line x1="312" y1="158" x2="312" y2={134-17*p} stroke="#c4d4e7" strokeWidth="3"/><path d="M304 144 L312 134 L320 144" fill="none" stroke="#c4d4e7" strokeWidth="3"/>
      <line x1="312" y1="201" x2="312" y2={225+17*p} stroke="#c4d4e7" strokeWidth="3"/><path d="M304 216 L312 226 L320 216" fill="none" stroke="#c4d4e7" strokeWidth="3"/>
      <rect x="610" y="76" width="160" height="187" rx="18" fill="#0d1b2b" stroke="#2a405b"/>
      <text x="632" y="111" fontSize="14" fontWeight="700" fill="#7186a4">LOAD FRAME</text>
      <text x="632" y="153" fontSize="30" fontWeight="800" fill="#dce8f8">{(load*p).toFixed(1)} kN</text>
      <text x="632" y="182" fontSize="13" fill="#6e829e">Target {load} kN</text>
      <text x="632" y="216" fontSize="13" fill="#6e829e">Crosshead</text><text x="632" y="238" fontSize="14" fontWeight="700" fill="#f2b84a">controlled</text>
      <path d="M 80 328 H 742" stroke="#31465f" strokeWidth="3"/><circle cx={80+662*p} cy="328" r="8" fill="#f2b84a"/>
    </svg>
    <div className="rig-label"><strong>Universal mechanical test frame</strong><span>Deformation is illustrative. Stress/strain evidence must come from a real measurement or validated simulation.</span></div>
  </div>;
}
