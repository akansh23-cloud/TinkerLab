import {render,screen} from "@testing-library/react";
import {VirtualEvaluationWarning} from "../VirtualEvaluationWarning";
// The banner legitimately contains the phrase "validated material properties" inside a negation,
// so the guard must assert the absence of an affirmative validation claim, not of a substring.
test("labels virtual evaluations as non-physical",()=>{
  render(<VirtualEvaluationWarning/>);
  expect(screen.getByText(/not physical experiments/i)).toBeInTheDocument();
  expect(screen.queryByText(/experimentally validated/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/^(?!.*\bnot\b).*validated material/i)).not.toBeInTheDocument();
});
