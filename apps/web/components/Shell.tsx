import Link from "next/link";

/**
 * Navigation is grouped by what the user is trying to do, not by which phase built it.
 * "Set up" holds the things that must exist before anything runs; the labs sit under the study
 * they belong to, which is why they are not top-level links.
 */
export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/">
          <div className="brand">TinkerLab</div>
          <div className="brand-sub">Material Replacement OS · Phase 12</div>
        </Link>
        <nav className="nav">
          <Link href="/">Dashboard</Link>

          <div className="nav-group">Materials</div>
          <Link href="/materials">Materials explorer</Link>
          <Link href="/explore">Property space chart</Link>
          <Link href="/materials/new">Record a material</Link>
          <Link href="/imports">Import center</Link>
          <Link href="/data-sources">External data sources</Link>

          <div className="nav-group">Studies</div>
          <Link href="/studies/new">New replacement study</Link>
          <Link href="/reasoning">Replacement reasoning</Link>
          <Link href="/validation">Experimental validation</Link>

          <div className="nav-group">Scientific core</div>
          <Link href="/simulation">Simulation Lab</Link>
        </nav>
        <div className="sidebar-foot">
          Evidence, governed external data, hypotheses, prediction, virtual campaigns, physics simulation,
          industrial viability and functional replacement reasoning.
          <br />
          <br />
          Simulation is computational evidence, not physical validation.
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
