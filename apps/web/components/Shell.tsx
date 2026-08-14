import Link from "next/link";
export function Shell({children}:{children:React.ReactNode}) {
  return <div className="shell">
    <aside className="sidebar">
      <Link href="/"><div className="brand">TinkerLab</div><div className="brand-sub">Material Replacement OS · Phase 11.1</div></Link>
      <nav className="nav">
        <Link href="/">Dashboard</Link>
        <Link href="/materials">Materials explorer</Link>
        <Link href="/imports">Import center</Link>
        <Link href="/data-sources">External data sources</Link>
        <Link href="/simulation">Simulation Lab</Link>
        <Link href="/reasoning">Replacement Reasoning</Link>
        <Link href="/validation">Experimental Validation</Link>
        <Link href="/projects/new">New replacement study</Link>
      </nav>
      <div style={{position:"absolute",bottom:24,left:18,right:18,fontSize:11,color:"#8ca299",lineHeight:1.5}}>
        Evidence + governed external data + hypotheses + prediction + virtual campaigns + physics simulation + industrial viability + functional replacement reasoning.<br/>Simulation is computational evidence, not physical validation.
      </div>
    </aside>
    <main className="main">{children}</main>
  </div>;
}
