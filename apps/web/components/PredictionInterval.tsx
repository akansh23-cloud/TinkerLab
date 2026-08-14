export function PredictionInterval({point,lower,upper,unit}:{point?:number;lower?:number;upper?:number;unit?:string}) {
  if (point === undefined || point === null) return <span className="muted">No numeric prediction</span>;
  return <span><strong>{Number(point).toFixed(2)} {unit??""}</strong>{lower!==undefined&&lower!==null&&upper!==undefined&&upper!==null&&<span className="muted"> · interval {Number(lower).toFixed(2)}–{Number(upper).toFixed(2)} {unit??""}</span>}</span>;
}
