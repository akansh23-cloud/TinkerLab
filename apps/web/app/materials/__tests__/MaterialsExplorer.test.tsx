import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, test, expect } from "vitest";
import MaterialsExplorer from "../page";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: vi.fn(async () => [{
      id:"m1",display_name:"Demo Polymer",canonical_name:"demo-polymer",material_family:"polymer",source_type:"seed_demo",
      is_seed_data:true,visibility:"public",identifiers:[{namespace:"tinkerlab",value:"TL-1",is_primary:true}],
      observation_count:8,evidence_types:["seed_demo"],conflict_count:1,
    }]),
  };
});

test("renders identity, evidence coverage and conflict state", async () => {
  const client = new QueryClient({defaultOptions:{queries:{retry:false}}});
  render(<QueryClientProvider client={client}><MaterialsExplorer/></QueryClientProvider>);
  expect(await screen.findByText("Demo Polymer")).toBeInTheDocument();
  expect(screen.getByText("TL-1")).toBeInTheDocument();
  expect(screen.getByText("8 observation(s)")).toBeInTheDocument();
  expect(screen.getByText("1 conflict")).toBeInTheDocument();
});
