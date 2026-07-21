# Buyer Discovery Plan — Evidence Case Pilot

**Status:** task 1 of the market-proof program  
**Purpose:** identify a budget-owning workflow before expanding product scope  
**Non-goal:** selling an unvalidated compliance product or collecting customer
data without consent

## Decision to make

Determine whether Issue Triage should be positioned as an **auditable engineering
evidence case** for teams making consequential software-quality decisions, and
identify the first buyer who owns that pain and can sponsor a pilot.

The current open-source maintainer workflow remains valid proof of capability;
it is not assumed to be the commercial customer.

## Buyer hypotheses to test

| Hypothesis | Potential buyer | Recurring decision | Evidence pain | Disconfirming signal |
| --- | --- | --- | --- | --- |
| H1: Engineering assurance | Engineering-quality, platform, or developer-productivity leader | Accept, defer, or close a behavior report in a large internal codebase | Reproduction work and later review are slow or inconsistent | Triage is cheap, informal, and no one owns a budget |
| H2: Incident/change review | Reliability, security, or incident-response engineering lead | Decide whether a report requires remediation or escalation | The team cannot reconstruct the test, environment, and reasoning later | Existing incident tooling already supplies trusted executable evidence |
| H3: Regulated engineering | Quality-system or engineering leader in a high-consequence domain | Sign off on evidence supporting a software-quality decision | Audit/review requires provenance across issue, test, environment, and reviewer | Policy does not require this evidence or the buyer cannot use external AI tooling |

These are hypotheses, not claims of regulatory compliance or product-market fit.

## Interview target

Conduct **12–15 discovery conversations** before committing to an enterprise
repositioning:

- 4–5 engineering-quality/platform/developer-productivity leaders;
- 3–5 reliability, security, or incident-response engineering leaders;
- 3–5 engineering or quality leaders in a high-consequence domain;
- optional: 2 experienced open-source maintainers as workflow comparators, not
  primary commercial buyers.

Recruit people who have personally reviewed a behavior report, defect claim,
or incident finding in the previous 90 days. Do not recruit only AI enthusiasts
or friends who cannot describe a real workflow.

## Interview protocol (30 minutes)

### 1. Ground in a recent event (10 minutes)

1. “Tell me about the last reported behavior issue your team had to investigate.”
2. “What made the report difficult to accept, reproduce, defer, or close?”
3. “Who touched the decision, and what evidence did each person need?”
4. “What happened after the decision—did anyone need to reconstruct it later?”

Do not demo the product until this section is complete. Record only consented,
bounded notes; never copy source code, credentials, customer data, or incident
details into this repository.

### 2. Quantify the current workflow (8 minutes)

1. “How long did reproduction take from report to a reviewable conclusion?”
2. “How many engineers/reviewers were involved?”
3. “What proportion of reports lack enough information?”
4. “What evidence is required to make the decision trusted?”
5. “Who experiences the cost, and who can fund a better workflow?”

### 3. Test the evidence-case concept (8 minutes)

Show the #7564 or #3563 evidence trail for no more than three minutes, then ask:

1. “Would a bounded case containing a changed test, JUnit failure, environment
   manifest, and reviewer approval help with your example? Why or why not?”
2. “Which artifact is indispensable? Which is noise?”
3. “What data or network restrictions would block this?”
4. “Would this be used as a triage aid, a review record, or neither?”
5. “Would a human approval gate be required for your workflow?”

### 4. Test commitment (4 minutes)

1. “Would you sponsor a four-week shadow pilot on a bounded repository or queue?”
2. “Who else must approve a pilot?”
3. “What must be true for you to call it successful?”
4. “Would you pay for this if it met that bar? What budget category would it
   come from?”

Never ask for a hypothetical price before the participant has described a real
workflow and a pilot-success criterion.

## Per-interview scorecard

For each conversation, score 0–2 and retain a short evidence-based note:

| Dimension | 0 | 1 | 2 |
| --- | --- | --- | --- |
| Pain frequency | Rare/ad hoc | Monthly | Weekly or higher |
| Decision consequence | Low | Moderate | Delays, risk, audit, or customer impact |
| Evidence burden | Informal opinion | Repro/test needed | Repro, provenance, and review needed |
| Existing-tool gap | Adequately solved | Partial workaround | No credible current solution |
| Budget ownership | None/unknown | Influencer identified | Buyer or sponsor identified |
| Pilot willingness | No | Revisit later | Bounded pilot commitment |
| Data/deployment feasibility | Blocked | Uncertain | Feasible with stated controls |

Maximum score: 14. Scores organize evidence; they do not manufacture demand.

## Decision gates

### Proceed to an enterprise Evidence Case build

Proceed only if all of the following are true:

- at least 10 interviews completed across at least two buyer hypotheses;
- at least three interviews score 10 or higher;
- at least two participants independently identify the same core workflow and
  required evidence;
- at least one named pilot sponsor agrees to a bounded shadow-pilot conversation;
- no non-negotiable data/deployment restriction makes the present architecture
  unusable for the selected workflow.

### Refine or remain maintainer-focused

Do not reframe the product as enterprise/compliance software if the interviews
show one or more of:

- no buyer owns the cost of triage evidence;
- existing issue/test/incident systems already solve the provenance problem;
- data policies prohibit the required model/sandbox flow with no viable
  deployment path;
- participants value the demo but will not sponsor a pilot;
- needs cluster around a different buyer or workflow than the hypotheses above.

## Pilot proposal template

Offer a **four-week, shadow-mode, no-write pilot** only after discovery support:

- one approved repository or bounded issue queue;
- no autonomous GitHub comments, closures, labels, or production changes;
- explicit data and retention agreement;
- a named internal reviewer/sponsor;
- agreed success metrics: time-to-evidence, reviewer time, semantic alignment,
  accepted/declined usefulness, and cost envelope;
- an exit path: delete pilot telemetry subject to the agreement; retain or remove
  evidence according to the partner's instruction and applicable consent.

## Required outputs from this task

1. An anonymized interview log outside the source tree or in an approved private
   workspace.
2. A one-page synthesis: repeated workflow, buyer, evidence artifacts valued,
   blockers, pilot interest, and direct quotes only with consent.
3. A go/no-go decision against the gates above.
4. If go: a product brief for task 2 specifying the Evidence Case workflow from
   the selected buyer's language.

## Guardrails

- Do not claim compliance certification, ROI, customer demand, accuracy, or
  willingness to pay before the corresponding evidence exists.
- Do not process proprietary source, issue bodies, secrets, or regulated data
  through the current local pilot without written authorization and a reviewed
  deployment/data path.
- Do not make public GitHub comments as part of discovery or pilot recruitment.
- Keep the existing human approval gate; discovery does not authorize relaxing
  public-action policy.
