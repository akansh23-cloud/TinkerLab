import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, test, expect } from "vitest";
import ImportCenter from "../page";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: vi.fn(async (path:string) => path.includes("preview") ? {
      payload_checksum:"abc",format:"json",valid:true,material_count:1,observation_count:1,warnings:[],errors:[],normalized_preview:[{display_name:"Imported Demo"}],
    } : {import_id:"i1",status:"committed",idempotent_replay:false,payload_checksum:"abc",summary:{materials_created:1},errors:[]}),
  };
});

test("requires dry-run validation before commit", async () => {
  const client = new QueryClient();
  render(<QueryClientProvider client={client}><ImportCenter/></QueryClientProvider>);
  const commit = screen.getByRole("button", {name:"Commit validated import"});
  expect(commit).toBeDisabled();
  fireEvent.change(screen.getByPlaceholderText('{"materials": [...]}'), {target:{value:'{"materials":[]}'}});
  fireEvent.click(screen.getByRole("button", {name:"Dry-run preview"}));
  expect(await screen.findByText("VALID")).toBeInTheDocument();
  expect(commit).not.toBeDisabled();
});
