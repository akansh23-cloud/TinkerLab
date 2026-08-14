// Shown wherever a recommendation or dossier is displayed. A scientific conclusion is not a
// commercial or regulatory authorization, and the interface must never let that distinction get
// lost between the recommendation and the reader.
export function QualificationNotice({note}:{note?:string}){
  return <div className="notice" role="note" data-testid="qualification-notice">
    <strong>Not a qualification decision.</strong>{" "}
    {note ?? "TinkerLab recommendations summarize available scientific, industrial and experimental evidence. They do not replace required regulatory, qualification, safety or customer approval processes, and they are not authorization to replace the incumbent material in production."}
  </div>;
}
