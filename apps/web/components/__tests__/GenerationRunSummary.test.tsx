import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { GenerationRun } from "@/lib/api";
import { GenerationRunSummary } from "../GenerationRunSummary";
const run:GenerationRun={id:"r",project_id:"p",organisation_id:"o",replacement_specification_checksum:"a".repeat(64),search_space_id:"s",search_space_version:1,search_space_checksum:"b".repeat(64),strategy_key:"bounded_composition_variation",strategy_version:"1.0",configuration_checksum:"c".repeat(64),random_seed:42,requested_candidate_budget:20,generated_count:5,accepted_count:3,rejected_count:1,duplicate_count:1,result_checksum:"d".repeat(64),status:"completed",created_by:"u",metadata:{},created_at:"2026-08-12T00:00:00Z"};
describe("GenerationRunSummary",()=>{it("shows auditable counts and checksums",()=>{render(<GenerationRunSummary run={run}/>);expect(screen.getByText(/5 generated/)).toBeInTheDocument();expect(screen.getByText(/42 \/ 20/)).toBeInTheDocument();expect(screen.getByText(/bounded_composition_variation/)).toBeInTheDocument();});});
