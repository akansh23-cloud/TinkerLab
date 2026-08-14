import type {VirtualCandidateEvaluation} from "@/lib/api";

type Props={evaluations:VirtualCandidateEvaluation[];xKey:string;yKey:string};
export function ParetoScatter({evaluations,xKey,yKey}:Props){
  const usable=evaluations.filter(e=>Number.isFinite(e.objective_vector[xKey]?.point)&&Number.isFinite(e.objective_vector[yKey]?.point));
  if(usable.length<2) return <div className="empty">At least two candidates with complete objective predictions are required for a 2D Pareto view.</div>;
  const xs=usable.map(e=>Number(e.objective_vector[xKey].point)); const ys=usable.map(e=>Number(e.objective_vector[yKey].point));
  const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
  const sx=(v:number)=>50+((v-minX)/(maxX-minX||1))*620; const sy=(v:number)=>330-((v-minY)/(maxY-minY||1))*270;
  return <div className="pareto-chart" data-testid="pareto-scatter">
    <svg viewBox="0 0 720 380" role="img" aria-label={`Pareto scatter of ${xKey} and ${yKey}`}>
      <line x1="50" y1="330" x2="680" y2="330" stroke="currentColor" opacity=".25"/><line x1="50" y1="50" x2="50" y2="330" stroke="currentColor" opacity=".25"/>
      <text x="365" y="370" textAnchor="middle" fontSize="12">{xKey} · {usable[0].objective_vector[xKey]?.unit??"unit"}</text>
      <text x="16" y="190" textAnchor="middle" fontSize="12" transform="rotate(-90 16 190)">{yKey} · {usable[0].objective_vector[yKey]?.unit??"unit"}</text>
      {usable.map(e=>{const x=Number(e.objective_vector[xKey].point),y=Number(e.objective_vector[yKey].point);const xi=e.objective_intervals[xKey],yi=e.objective_intervals[yKey];const xlo=xi?.lower!==undefined?sx(Number(xi.lower)):sx(x),xhi=xi?.upper!==undefined?sx(Number(xi.upper)):sx(x);const ylo=yi?.lower!==undefined?sy(Number(yi.lower)):sy(y),yhi=yi?.upper!==undefined?sy(Number(yi.upper)):sy(y);return <g key={e.id}>
        <line x1={xlo} y1={sy(y)} x2={xhi} y2={sy(y)} stroke="currentColor" opacity=".25"/><line x1={sx(x)} y1={ylo} x2={sx(x)} y2={yhi} stroke="currentColor" opacity=".25"/>
        <circle cx={sx(x)} cy={sy(y)} r={e.selected_as_parent?7:5} fill="currentColor" opacity={e.pareto_rank===1?1:.45}/>
        <text x={sx(x)+8} y={sy(y)-7} fontSize="10">{e.pareto_rank?`P${e.pareto_rank}`:"incomplete"}{e.selected_as_parent?" · parent":""}</text>
        <title>{`${e.candidate_id} · ${e.feasibility_class} · ${xKey} ${x} · ${yKey} ${y}`}</title>
      </g>})}
    </svg>
    <div className="muted">Point estimates are plotted with interval bars. Darker P1 points are Pareto-front candidates within this campaign; labels, not color alone, carry feasibility/rank meaning.</div>
  </div>;
}
